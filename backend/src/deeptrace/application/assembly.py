"""Assemble a production-shaped harness runtime from application settings."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langgraph.checkpoint.base import BaseCheckpointSaver
from tavily import TavilyClient

from deeptrace.application.model_provider import build_model_gateway
from deeptrace.application.research import ResearchApplicationService
from deeptrace.config import Settings
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.model_budget import BudgetStateUnavailable, RunBudgetModelGateway
from deeptrace.harness.model_gateway import ChatModelGateway
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.harness.token_budget import TokenBudgetConfig
from deeptrace.research.runtime import build_controller_research_graph
from deeptrace.observability.events import HarnessEventRecorder
from deeptrace.persistence.execution_ledger import SqlAlchemyToolExecutionStore
from deeptrace.persistence.memory_store import SqlAlchemyMemoryStore
from deeptrace.persistence.model_budget import SqlAlchemyModelBudgetStore
from deeptrace.persistence.schema import ensure_sqlite_schema as _ensure_sqlite_schema
from deeptrace.responses import (
    build_answer_graph,
    build_brief_graph,
    build_report_graph,
)
from deeptrace.tools import AgentToolGateway, build_research_tool_registry
from deeptrace.tools.budget import (
    BudgetScopeKey,
    BudgetUnits,
    InMemoryBudgetManager,
)
from deeptrace.tools.cache import InMemorySuccessCache, SuccessCacheSingleflight
from deeptrace.tools.evidence_store import EvidenceStore
from deeptrace.tools.execution_store import (
    ToolExecutionStore,
)
from deeptrace.tools.policy import (
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
)
from deeptrace.tools.scraper import AsyncWebFetcher
from deeptrace.tools.search import ToolContext
from deeptrace.tools.search.tavily import search_web


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class _SeededBudgets:
    """Budget facade that seeds consumed units from the durable ledger once,
    before the first reservation, so resumed runs keep their original budget."""

    def __init__(self, inner, seed, run_id: str) -> None:
        self._inner = inner
        self._seed = seed
        self._run_id = run_id
        self._loaded = False
        self._load_lock = asyncio.Lock()

    async def _ensure(self) -> None:
        if self._loaded:
            return
        async with self._load_lock:
            if self._loaded:
                return
            try:
                consumed = await self._seed()
                if consumed:
                    expanded: dict[BudgetScopeKey, BudgetUnits] = {}
                    run_total = BudgetUnits()
                    mode_totals: dict[ResearchMode, BudgetUnits] = {}
                    for (mode_value, caller), units in consumed.items():
                        mode = ResearchMode(mode_value)
                        expanded[
                            BudgetScopeKey.for_agent(self._run_id, mode, caller)
                        ] = units
                        run_total = run_total.plus(units)
                        mode_totals[mode] = mode_totals.get(mode, BudgetUnits()).plus(
                            units
                        )
                    expanded[BudgetScopeKey.for_run(self._run_id)] = run_total
                    for mode, units in mode_totals.items():
                        expanded[BudgetScopeKey.for_mode(self._run_id, mode)] = units
                    await self._inner.seed_consumed(expanded)
            except Exception as exc:
                logging.getLogger(__name__).exception(
                    "failed to rebuild budget usage for run %s; "
                    "dispatch denied until budget recovery succeeds",
                    self._run_id,
                )
                raise BudgetStateUnavailable() from exc
            self._loaded = True

    async def reserve(self, scope, requested):
        await self._ensure()
        return await self._inner.reserve(scope, requested)

    async def commit(self, receipt, units):
        return await self._inner.commit(receipt, units)

    async def release(self, receipt):
        return await self._inner.release(receipt)


def _budgets_for_run(run_id: str, settings: Settings) -> InMemoryBudgetManager:
    limit = BudgetUnits(
        tool_calls=settings.max_tool_calls,
        network_requests=settings.max_tool_calls,
        fetched_pages=settings.max_fetched_pages,
    )
    scopes: list[BudgetScopeKey] = [BudgetScopeKey.for_run(run_id)]
    for mode in ResearchMode:
        scopes.append(BudgetScopeKey.for_mode(run_id, mode))
        for caller in ("workflow-graph", "plan-execute-executor"):
            scopes.append(BudgetScopeKey.for_agent(run_id, mode, caller))
        for index in range(6):
            scopes.append(BudgetScopeKey.for_agent(run_id, mode, f"researcher-{index}"))
    return InMemoryBudgetManager({scope: limit for scope in scopes})


def _build_durable_stores(
    settings: Settings, runs_dir: Path | str | None
) -> tuple[
    BaseCheckpointSaver,
    ToolExecutionStore,
    Any,
    EvidenceStore,
    Any,
    SqlAlchemyModelBudgetStore,
]:
    """Checkpoint saver, execution ledger, memory store, evidence store.

    Distributed (MySQL DSN configured): the checkpointer, tool ledger, memory
    store and Evidence store are SQL-backed and shared across processes.
    Local: the checkpointer, Evidence store and long-term memory store persist
    to a SQLite file under ``runs_dir`` (one shared instance per process, so a
    thread's later turns see earlier evidence/memory and a restart keeps them),
    including the tool ledger and model admission snapshots.
    """
    from deeptrace.persistence.checkpoint import SqlAlchemyCheckpointSaver
    from deeptrace.persistence.database import create_session_factory
    from deeptrace.persistence.evidence_store import SqlAlchemyEvidenceStore

    dsn = getattr(settings, "mysql_dsn", "")
    if dsn:
        engine, sessions = create_session_factory(dsn)
        saver = SqlAlchemyCheckpointSaver(sessions)
        ledger: ToolExecutionStore = SqlAlchemyToolExecutionStore(sessions)
        memory_store: Any = SqlAlchemyMemoryStore(sessions)
        evidence = SqlAlchemyEvidenceStore(sessions)
        return saver, ledger, memory_store, evidence, engine, SqlAlchemyModelBudgetStore(sessions)

    runs = Path(runs_dir or "runs")
    runs.mkdir(parents=True, exist_ok=True)
    db_path = (runs / "harness_checkpoints.db").resolve()
    engine, sessions = create_session_factory(f"sqlite+aiosqlite:///{db_path}")

    _ensure_sqlite_schema(db_path)
    saver = SqlAlchemyCheckpointSaver(sessions)
    ledger = SqlAlchemyToolExecutionStore(sessions)
    memory_store = SqlAlchemyMemoryStore(sessions)
    evidence = SqlAlchemyEvidenceStore(sessions)
    return saver, ledger, memory_store, evidence, engine, SqlAlchemyModelBudgetStore(sessions)


def _build_memory_retriever(
    settings: Settings,
    memory_store: Any,
    *,
    runs_dir: Path | str | None,
) -> Any | None:
    if settings.memory_retrieval != "semantic":
        return None

    import chromadb
    from chromadb.config import Settings as ChromaSettings

    from deeptrace.harness.memory.embedding import BgeM3EmbeddingGateway
    from deeptrace.harness.memory.retriever import SemanticMemoryRetriever
    from deeptrace.persistence.chroma_memory import ChromaMemoryVectorIndex

    if settings.chroma_url:
        parsed = urlparse(settings.chroma_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("DEEPTRACE_CHROMA_URL must be an http(s) URL")
        client = chromadb.HttpClient(
            host=parsed.hostname,
            port=parsed.port or (443 if parsed.scheme == "https" else 80),
            ssl=parsed.scheme == "https",
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    else:
        persist_path = settings.chroma_persist_path
        if not persist_path.is_absolute() and runs_dir is not None:
            persist_path = Path(runs_dir) / persist_path
        persist_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(persist_path.resolve()),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    embeddings = BgeM3EmbeddingGateway(
        settings.embedding_model_path,
        batch_size=settings.embedding_batch_size,
    )
    index = ChromaMemoryVectorIndex(client, settings.chroma_collection)
    return SemanticMemoryRetriever(memory_store, embeddings, index)


class HarnessRuntimeBundle:
    """The assembled runtime plus a lifecycle hook for its owned resources.

    ``aclose()`` disposes the SQL engine/connection pool and the HTTP/browser
    clients owned by the fetcher. API and Worker lifecycles must call it on
    shutdown.
    """

    def __init__(
        self,
        service: ResearchApplicationService,
        context_factory: Callable[[str], HarnessContext],
        resources: list[Any],
        release_run: Callable[[str], None],
    ) -> None:
        self.service = service
        self.context_factory = context_factory
        self.release_run = release_run
        self._resources = [item for item in resources if item is not None]

    async def aclose(self) -> None:
        logger = logging.getLogger(__name__)
        for resource in self._resources:
            closer = getattr(resource, "aclose", None) or getattr(
                resource, "dispose", None
            )
            if closer is None:
                continue
            try:
                result = closer()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # resource cleanup must never mask the original shutdown path,
                # but it must be visible
                logger.exception(
                    "failed to close harness resource %s",
                    type(resource).__name__,
                )
        from langsmith import utils as langsmith_utils
        from langsmith.run_trees import get_cached_client

        if langsmith_utils.tracing_is_enabled():
            try:
                await asyncio.to_thread(get_cached_client().flush, timeout=10)
            except Exception:
                logger.exception("failed to flush LangSmith traces during shutdown")


def build_harness_runtime(
    settings: Settings,
    *,
    runs_dir: Path | str | None = None,
) -> HarnessRuntimeBundle:
    """Assemble the top-level runtime graph plus a per-run context factory.

    The graph is always compiled with a durable checkpointer (MySQL when a DSN
    is configured, otherwise a SQLite file under ``runs_dir``), so any run can
    resume node-by-node after a crash or restart.
    """
    saver, ledger, memory_store, evidence_store, engine, model_budget_store = _build_durable_stores(
        settings, runs_dir
    )
    memory_retriever = _build_memory_retriever(
        settings, memory_store, runs_dir=runs_dir
    )

    model_gateway = build_model_gateway(settings, ChatModelGateway)

    fetcher = AsyncWebFetcher(
        min_chars=settings.min_extracted_chars,
        min_tokens=settings.min_extracted_tokens,
        max_page_chars=settings.max_page_chars,
        allow_benchmark_dns_proxy=settings.allow_benchmark_dns_proxy,
    )

    strategies = StrategyRegistry()
    executor = build_batch_research_graph(
        token_budget=TokenBudgetConfig(
            context_tokens=settings.model_context_tokens,
            output_reserve_tokens=settings.openai_max_tokens or 4096,
            safety_tokens=settings.context_safety_tokens,
        ),
        source_target=settings.research_source_target,
    )
    if settings.research_orchestrator in {"controller", "strategies", "legacy"}:
        for mode in ResearchMode:
            strategies.register(StrategyRegistration(mode, build_controller_research_graph(
                executor, mode=mode, max_tasks=min(6, settings.search_query_count),
                max_parallel=1 if mode is ResearchMode.PLAN_EXECUTE else 4,
                max_rounds=2,
            )))
    else:
        raise ValueError("unknown research_orchestrator")
    # Budget is a guardrail, not a compressor: reserve output tokens first so
    # generation always has room, and only trim elastic segments when an input
    # actually approaches the model window.
    response_budget = TokenBudgetConfig(
        context_tokens=settings.model_context_tokens,
        output_reserve_tokens=settings.openai_max_tokens or 4_096,
        safety_tokens=settings.context_safety_tokens,
    )
    responses = ResponseGraphRegistry()
    responses.register(
        ResponseRegistration(ResponseMode.ANSWER, build_answer_graph(response_budget))
    )
    responses.register(
        ResponseRegistration(ResponseMode.BRIEF, build_brief_graph(response_budget))
    )
    responses.register(
        ResponseRegistration(ResponseMode.REPORT, build_report_graph(response_budget))
    )
    graph = build_agent_runtime_graph(strategies, responses, checkpointer=saver)
    service = ResearchApplicationService(graph)
    run_model_gateways: dict[str, RunBudgetModelGateway] = {}
    run_recorders: dict[str, HarnessEventRecorder] = {}

    def context_factory(run_id: str, on_event=None) -> HarnessContext:
        recorder = run_recorders.setdefault(run_id, HarnessEventRecorder(run_id=run_id))
        if run_id not in run_model_gateways:
            run_model_gateways[run_id] = RunBudgetModelGateway(
                model_gateway, max_calls=settings.max_model_calls,
                run_id=run_id, store=model_budget_store, event_sink=recorder,
                max_input_tokens=settings.max_input_tokens,
                finishing_input_reserve=min(20_000, settings.max_input_tokens // 5),
                max_seconds=settings.research_max_seconds,
                finishing_calls=(
                    min(3, settings.max_model_calls - 1)
                    if settings.response_fact_review else 2
                ),
            )
        if on_event is not None:
            recorder.on_sync_event = on_event
        tool_context = ToolContext(tavily=TavilyClient(api_key=settings.tavily_api_key))

        def run_search(query: str, **options) -> Any:
            return search_web(tool_context, query, **options)

        registry = build_research_tool_registry(
            search=run_search,
            fetcher=fetcher,
            evidence_store=evidence_store,
        )
        # Crash-safe budgeting: when the ledger is durable, consumed units are
        # seeded from it once before the first reservation, so a resumed run
        # cannot exceed its original allowance.
        budgets: Any = _budgets_for_run(run_id, settings)
        if isinstance(ledger, SqlAlchemyToolExecutionStore):
            budgets = _SeededBudgets(
                budgets,
                lambda: ledger.tool_usage_for_run(run_id),
                run_id,
            )
        tool_gateway = AgentToolGateway(
            registry=registry,
            allowlist=StaticToolAllowlist(),
            security=DeterministicUrlSecurityPolicy(),
            budgets=budgets,
            executions=ledger,
            cache=SuccessCacheSingleflight(InMemorySuccessCache()),
            evidence_store=evidence_store,
            event_sink=recorder,
            retry_attempts=settings.agent_tool_retry_attempts,
            retry_base_seconds=settings.agent_tool_retry_base_seconds,
        )
        # Single-tenant deployment: the current API surface has no
        # authentication boundary, so all runs share one workspace namespace.
        # Multi-tenant isolation requires an authenticated identity injected
        # here (user_id/workspace_id) before Memory/Evidence scoping claims
        # can extend beyond this demo positioning.
        return HarnessContext(
            user_id="local-user",
            workspace_id="local-workspace",
            model_gateway=run_model_gateways[run_id],
            tool_gateway=tool_gateway,
            evidence_store=evidence_store,
            event_sink=recorder,
            clock=_SystemClock(),
            memory_store=memory_store,
            memory_retriever=memory_retriever,
            memory_recall_limit=settings.memory_top_k,
            research_max_pages=settings.agent_max_pages,
            response_fact_review=settings.response_fact_review,
            research_completion_scope=settings.research_completion_scope,
        )

    def release_run(run_id: str) -> None:
        run_model_gateways.pop(run_id, None)
        run_recorders.pop(run_id, None)

    return HarnessRuntimeBundle(service, context_factory, [engine, fetcher], release_run)
