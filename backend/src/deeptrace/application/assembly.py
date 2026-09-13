"""Assemble a production-shaped harness runtime from application settings."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tavily import TavilyClient

from deeptrace.application.research import ResearchApplicationService
from deeptrace.config import Settings
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.model_gateway import ChatModelGateway
from deeptrace.harness.memory.store import InMemoryMemoryStore
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.memory import ResearchMemory
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
from deeptrace.tools.evidence_store import EvidenceStore, InMemoryEvidenceStore
from deeptrace.tools.execution_store import (
    InMemoryToolExecutionStore,
    ToolExecutionStore,
)
from deeptrace.tools.policy import (
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
)
from deeptrace.tools.search import ToolContext
from deeptrace.tools.search.tavily import search_web
from deeptrace.tools.scraper import AsyncWebFetcher


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


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
    from deeptrace.persistence.orm import Base

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
        return saver, ledger, memory_store, evidence

    runs = Path(runs_dir or "runs")
    runs.mkdir(parents=True, exist_ok=True)
    db_path = (runs / "harness_checkpoints.db").resolve()
    engine, sessions = create_session_factory(f"sqlite+aiosqlite:///{db_path}")

    _ensure_sqlite_schema(db_path)
    saver = SqlAlchemyCheckpointSaver(sessions)
    ledger = InMemoryToolExecutionStore()
    memory_store = InMemoryMemoryStore()
    evidence = SqlAlchemyEvidenceStore(sessions)
    return saver, ledger, memory_store, evidence


def _ensure_sqlite_schema(db_path: Path) -> None:
    """Create the checkpoint tables synchronously (safe inside a running loop)."""
    import sqlite3

    from sqlalchemy import create_engine
    from sqlalchemy.schema import CreateIndex, CreateTable

    from deeptrace.persistence.orm import (
        CheckpointRow,
        CheckpointWriteRow,
        EvidenceRecordRow,
    )

    sync_engine = create_engine("sqlite://")
    statements: list[str] = []
    for table in (
        CheckpointRow.__table__,
        CheckpointWriteRow.__table__,
        EvidenceRecordRow.__table__,
    ):
        statements.append(str(CreateTable(table).compile(sync_engine)))
        for index in table.indexes:
            statements.append(str(CreateIndex(index).compile(sync_engine)))
    connection = sqlite3.connect(db_path)
    try:
        for statement in statements:
            connection.execute(
                statement.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS")
                .replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS")
                .replace("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS")
            )
        connection.commit()
    finally:
        connection.close()


def build_harness_runtime(
    settings: Settings,
    *,
    runs_dir: Path | str | None = None,
    page_memory: ResearchMemory | None = None,
) -> tuple[ResearchApplicationService, Callable[[str], HarnessContext]]:
    """Assemble the top-level runtime graph plus a per-run context factory.

    The graph is always compiled with a durable checkpointer (MySQL when a DSN
    is configured, otherwise a SQLite file under ``runs_dir``), so any run can
    resume node-by-node after a crash or restart.
    """
    saver, ledger, memory_store, evidence_store = _build_durable_stores(
        settings, runs_dir
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
            memory=page_memory,
        )
        tool_gateway = AgentToolGateway(
            registry=registry,
            allowlist=StaticToolAllowlist(),
            security=DeterministicUrlSecurityPolicy(),
            budgets=_budgets_for_run(run_id),
            executions=ledger,
            cache=SuccessCacheSingleflight(InMemorySuccessCache()),
            evidence_store=evidence_store,
            event_sink=recorder,
        )
        return HarnessContext(
            user_id="local-user",
            workspace_id="local-workspace",
            model_gateway=model_gateway,
            tool_gateway=tool_gateway,
            evidence_store=evidence_store,
            event_sink=recorder,
            clock=_SystemClock(),
            memory_store=memory_store,
        )

    return service, context_factory
