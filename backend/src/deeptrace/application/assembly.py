"""Assemble a production-shaped harness runtime from application settings."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from tavily import TavilyClient

from deeptrace.application.research import ResearchApplicationService
from deeptrace.config import Settings
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.memory.store import InMemoryMemoryStore
from deeptrace.harness.model_gateway import ChatModelGateway
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.observability.events import HarnessEventRecorder
from deeptrace.responses import (
    build_answer_graph,
    build_brief_graph,
    build_report_graph,
)
from deeptrace.strategies import (
    build_multi_agent_research_graph,
    build_plan_execute_research_graph,
    build_research_topic_graph,
    build_workflow_research_graph,
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
    InMemoryToolExecutionStore,
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
                        mode_totals[mode] = mode_totals.get(
                            mode, BudgetUnits()
                        ).plus(units)
                    expanded[BudgetScopeKey.for_run(self._run_id)] = run_total
                    for mode, units in mode_totals.items():
                        expanded[BudgetScopeKey.for_mode(self._run_id, mode)] = units
                    await self._inner.seed_consumed(expanded)
            except Exception:
                logging.getLogger(__name__).exception(
                    "failed to rebuild budget usage for run %s; "
                    "continuing with fresh counters",
                    self._run_id,
                )
            finally:
                self._loaded = True

    async def reserve(self, scope, requested):
        await self._ensure()
        return await self._inner.reserve(scope, requested)

    async def commit(self, receipt, units):
        return await self._inner.commit(receipt, units)

    async def release(self, receipt):
        return await self._inner.release(receipt)


def _budgets_for_run(run_id: str) -> InMemoryBudgetManager:
    limit = BudgetUnits(tool_calls=60, network_requests=90, fetched_pages=60)
    scopes: list[BudgetScopeKey] = [BudgetScopeKey.for_run(run_id)]
    for mode in ResearchMode:
        scopes.append(BudgetScopeKey.for_mode(run_id, mode))
        for caller in ("workflow-graph", "plan-execute-executor"):
            scopes.append(BudgetScopeKey.for_agent(run_id, mode, caller))
        for index in range(6):
            scopes.append(
                BudgetScopeKey.for_agent(run_id, mode, f"researcher-{index}")
            )
    return InMemoryBudgetManager({scope: limit for scope in scopes})


def _build_durable_stores(
    settings: Settings, runs_dir: Path | str | None
) -> tuple[
    BaseCheckpointSaver,
    ToolExecutionStore,
    Any,
    EvidenceStore,
    Any,
]:
    """Checkpoint saver, execution ledger, memory store, evidence store.

    Distributed (MySQL DSN configured): the checkpointer, tool ledger, memory
    store and Evidence store are SQL-backed and shared across processes.
    Local: the checkpointer and Evidence store persist to a SQLite file under
    ``runs_dir`` (one shared instance per process, so a thread's later turns
    see earlier evidence and a restart keeps page bodies), while the ledger
    and memory store stay process-local per the documented Local guarantees.
    """
    from deeptrace.persistence.checkpoint import SqlAlchemyCheckpointSaver
    from deeptrace.persistence.database import create_session_factory
    from deeptrace.persistence.evidence_store import SqlAlchemyEvidenceStore

    dsn = getattr(settings, "mysql_dsn", "")
    if dsn:
        from deeptrace.persistence.execution_ledger import (
            SqlAlchemyToolExecutionStore,
        )
        from deeptrace.persistence.memory_store import SqlAlchemyMemoryStore

        engine, sessions = create_session_factory(dsn)
        saver = SqlAlchemyCheckpointSaver(sessions)
        ledger: ToolExecutionStore = SqlAlchemyToolExecutionStore(sessions)
        memory_store: Any = SqlAlchemyMemoryStore(sessions)
        evidence = SqlAlchemyEvidenceStore(sessions)
        return saver, ledger, memory_store, evidence, engine

    runs = Path(runs_dir or "runs")
    runs.mkdir(parents=True, exist_ok=True)
    db_path = (runs / "harness_checkpoints.db").resolve()
    engine, sessions = create_session_factory(f"sqlite+aiosqlite:///{db_path}")

    _ensure_sqlite_schema(db_path)
    saver = SqlAlchemyCheckpointSaver(sessions)
    ledger = InMemoryToolExecutionStore()
    memory_store = InMemoryMemoryStore()
    evidence = SqlAlchemyEvidenceStore(sessions)
    return saver, ledger, memory_store, evidence, engine


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


def _ensure_sqlite_schema(db_path: Path) -> None:
    """Create/migrate the local SQLite schema synchronously.

    Order matters for databases created by earlier builds:
    1. create tables (IF NOT EXISTS),
    2. add missing columns and backfill them,
    3. only then create indexes (they reference the new columns).
    """
    import hashlib
    import sqlite3

    from sqlalchemy import create_engine
    from sqlalchemy.schema import CreateIndex, CreateTable

    from deeptrace.persistence.orm import (
        CheckpointRow,
        CheckpointWriteRow,
        EvidenceRecordRow,
        ThreadLeaseRow,
    )

    sync_engine = create_engine("sqlite://")
    table_statements = [
        str(CreateTable(table).compile(sync_engine))
        for table in (
            CheckpointRow.__table__,
            CheckpointWriteRow.__table__,
            EvidenceRecordRow.__table__,
            ThreadLeaseRow.__table__,
        )
    ]
    index_statements = [
        str(CreateIndex(index).compile(sync_engine))
        for table in (
            CheckpointRow.__table__,
            CheckpointWriteRow.__table__,
            EvidenceRecordRow.__table__,
        )
        for index in table.indexes
    ]

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "PRAGMA table_info(evidence_records)"
        )  # ensure the file exists before CREATE IF NOT EXISTS runs
        for statement in table_statements:
            connection.execute(statement.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS"))

        def _columns(table: str) -> set[str]:
            return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}

        # column migration + backfill BEFORE the version index exists
        evidence_columns = _columns("evidence_records")
        connection.create_function(
            "deeptrace_sha256_hex",
            1,
            lambda value: hashlib.sha256((value or "").encode("utf-8")).hexdigest(),
        )
        if "canonical_url_hash" not in evidence_columns:
            connection.execute(
                "ALTER TABLE evidence_records "
                "ADD COLUMN canonical_url_hash VARCHAR(64)"
            )
            connection.execute(
                "UPDATE evidence_records "
                "SET canonical_url_hash = deeptrace_sha256_hex(canonical_url)"
            )
        elif connection.execute(
            "SELECT COUNT(*) FROM evidence_records "
            "WHERE canonical_url_hash IS NULL OR canonical_url_hash = ''"
        ).fetchone()[0]:
            connection.execute(
                "UPDATE evidence_records "
                "SET canonical_url_hash = deeptrace_sha256_hex(canonical_url) "
                "WHERE canonical_url_hash IS NULL OR canonical_url_hash = ''"
            )

        for statement in index_statements:
            connection.execute(
                statement.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS")
                .replace("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS")
            )
        connection.commit()
    finally:
        connection.close()


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
    ) -> None:
        self.service = service
        self.context_factory = context_factory
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
    saver, ledger, memory_store, evidence_store, engine = (
        _build_durable_stores(settings, runs_dir)
    )
    memory_retriever = _build_memory_retriever(
        settings, memory_store, runs_dir=runs_dir
    )

    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0,
        max_tokens=settings.openai_max_tokens,
    )
    model_gateway = ChatModelGateway(model)

    fetcher = AsyncWebFetcher(
        min_chars=settings.min_extracted_chars,
        min_tokens=settings.min_extracted_tokens,
        max_page_chars=settings.max_page_chars,
        allow_benchmark_dns_proxy=settings.allow_benchmark_dns_proxy,
    )

    strategies = StrategyRegistry()
    topic = build_research_topic_graph()
    strategies.register(
        StrategyRegistration(
            ResearchMode.WORKFLOW, build_workflow_research_graph(topic)
        )
    )
    strategies.register(
        StrategyRegistration(
            ResearchMode.PLAN_EXECUTE, build_plan_execute_research_graph(topic)
        )
    )
    strategies.register(
        StrategyRegistration(
            ResearchMode.MULTI_AGENT, build_multi_agent_research_graph(topic)
        )
    )
    responses = ResponseGraphRegistry()
    responses.register(
        ResponseRegistration(ResponseMode.ANSWER, build_answer_graph())
    )
    responses.register(
        ResponseRegistration(ResponseMode.BRIEF, build_brief_graph())
    )
    responses.register(
        ResponseRegistration(ResponseMode.REPORT, build_report_graph())
    )
    graph = build_agent_runtime_graph(strategies, responses, checkpointer=saver)
    service = ResearchApplicationService(graph)

    def context_factory(run_id: str, on_event=None) -> HarnessContext:
        from deeptrace.persistence.execution_ledger import (
            SqlAlchemyToolExecutionStore,
        )

        recorder = HarnessEventRecorder(run_id=run_id)
        if on_event is not None:
            recorder.on_sync_event = on_event
        tool_context = ToolContext(
            tavily=TavilyClient(api_key=settings.tavily_api_key)
        )

        def run_search(query: str) -> Any:
            return search_web(tool_context, query, max_results=5)

        registry = build_research_tool_registry(
            search=run_search,
            fetcher=fetcher,
        )
        # Crash-safe budgeting: when the ledger is durable, consumed units are
        # seeded from it once before the first reservation, so a resumed run
        # cannot exceed its original allowance.
        budgets: Any = _budgets_for_run(run_id)
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
        )
        # Single-tenant deployment: the current API surface has no
        # authentication boundary, so all runs share one workspace namespace.
        # Multi-tenant isolation requires an authenticated identity injected
        # here (user_id/workspace_id) before Memory/Evidence scoping claims
        # can extend beyond this demo positioning.
        return HarnessContext(
            user_id="local-user",
            workspace_id="local-workspace",
            model_gateway=model_gateway,
            tool_gateway=tool_gateway,
            evidence_store=evidence_store,
            event_sink=recorder,
            clock=_SystemClock(),
            memory_store=memory_store,
            memory_retriever=memory_retriever,
            memory_recall_limit=settings.memory_top_k,
        )

    return HarnessRuntimeBundle(
        service, context_factory, [engine, fetcher]
    )
