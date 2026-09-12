"""Shared scripted-gateway fixtures for strategy subgraph tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deeptrace.harness.context import HarnessContext
from deeptrace.domain import ResearchMode
from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.tools import AgentToolGateway, build_research_tool_registry
from deeptrace.tools.budget import BudgetScopeKey, BudgetUnits, InMemoryBudgetManager
from deeptrace.tools.cache import InMemorySuccessCache, SuccessCacheSingleflight
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from deeptrace.tools.execution_store import InMemoryToolExecutionStore
from deeptrace.tools.policy import (
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
    ToolCaller,
)


TENANT_ID = "workspace-1"
FIXED_NOW = datetime(2026, 9, 12, 8, 0, 0, tzinfo=UTC)


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))


class NoopModelGateway:
    async def invoke(self, *, role: str, messages: list[Any]) -> Any:
        raise AssertionError("topic graphs must not invoke the model gateway")


class RecordingToolGateway:
    """Wraps the real gateway and records every execute call."""

    def __init__(self, inner: AgentToolGateway) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any):
        self.calls.append(kwargs)
        return await self._inner.execute(**kwargs)


class ScriptedSearch:
    def __init__(
        self,
        *,
        results_by_query: dict[str, list[dict[str, str]]] | None = None,
        default_results: list[dict[str, str]] | None = None,
        fail: bool = False,
    ) -> None:
        self._results_by_query = results_by_query or {}
        self._default_results = default_results
        self._fail = fail
        self.calls: list[str] = []

    async def __call__(self, query: str) -> dict[str, Any]:
        self.calls.append(query)
        if self._fail:
            raise RuntimeError("provider exploded")
        results = self._results_by_query.get(query, self._default_results)
        return {"ok": True, "results": list(results or [])}


class ScriptedFetcher:
    """Maps URL to a canned page body; ``failures`` forces empty/raise modes."""

    def __init__(
        self,
        *,
        pages: dict[str, str] | None = None,
        failures: dict[str, str] | None = None,
    ) -> None:
        self._pages = pages or {}
        self._failures = failures or {}
        self.calls: list[str] = []

    async def fetch(self, url: str) -> RawDocument:
        self.calls.append(url)
        failure = self._failures.get(url)
        if failure == "raise":
            raise RuntimeError("scraper exploded")
        status = "failed" if failure else "success"
        return RawDocument(
            doc_id=f"doc-{len(self.calls)}",
            requested_url=url,
            final_url=url,
            canonical_url=url,
            title=f"Page {url}",
            content=self._pages.get(url, f"body for {url}"),
            content_hash=f"hash-{len(self.calls)}",
            fetched_at=FIXED_NOW,
            scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
            status=status,
        )


@dataclass
class GatewayFixture:
    gateway: RecordingToolGateway
    evidence_store: InMemoryEvidenceStore
    events: RecordingEventSink
    search: ScriptedSearch
    fetcher: ScriptedFetcher
    budgets: InMemoryBudgetManager
    context: HarnessContext

    async def evidence_id_for(self, url: str) -> str:
        evidence = await self.evidence_store.latest_for_source(TENANT_ID, url)
        return evidence.id


def build_gateway_fixture(
    *,
    run_ids: tuple[str, ...] = ("run-1", "run-2"),
    search_results: dict[str, list[dict[str, str]]] | None = None,
    default_search_results: list[dict[str, str]] | None = None,
    search_fail: bool = False,
    pages: dict[str, str] | None = None,
    fetch_failures: dict[str, str] | None = None,
    model_gateway: Any | None = None,
    evidence_store: InMemoryEvidenceStore | None = None,
) -> GatewayFixture:
    search = ScriptedSearch(
        results_by_query=search_results,
        default_results=default_search_results,
        fail=search_fail,
    )
    fetcher = ScriptedFetcher(pages=pages, failures=fetch_failures)
    registry = build_research_tool_registry(search=search, fetcher=fetcher)
    limit = BudgetUnits(tool_calls=50, network_requests=50, fetched_pages=50)
    caller_ids = (
        "workflow-graph",
        "plan-execute-executor",
        *(f"researcher-{index}" for index in range(6)),
    )
    scopes: list[BudgetScopeKey] = [
        BudgetScopeKey.for_run(run_id) for run_id in run_ids
    ]
    for run_id in run_ids:
        for mode in ResearchMode:
            scopes.append(BudgetScopeKey.for_mode(run_id, mode))
            for caller_id in caller_ids:
                scopes.append(BudgetScopeKey.for_agent(run_id, mode, caller_id))
    budgets = InMemoryBudgetManager({scope: limit for scope in scopes})
    evidence_store = evidence_store or InMemoryEvidenceStore()
    events = RecordingEventSink()
    inner = AgentToolGateway(
        registry=registry,
        allowlist=StaticToolAllowlist(),
        security=DeterministicUrlSecurityPolicy(),
        budgets=budgets,
        executions=InMemoryToolExecutionStore(),
        cache=SuccessCacheSingleflight(InMemorySuccessCache()),
        evidence_store=evidence_store,
        event_sink=events,
    )
    gateway = RecordingToolGateway(inner)
    context = HarnessContext(
        user_id="user-1",
        workspace_id=TENANT_ID,
        model_gateway=model_gateway or NoopModelGateway(),
        tool_gateway=gateway,
        evidence_store=evidence_store,
        event_sink=events,
        clock=FixedClock(),
    )
    return GatewayFixture(
        gateway=gateway,
        evidence_store=evidence_store,
        events=events,
        search=search,
        fetcher=fetcher,
        budgets=budgets,
        context=context,
    )


class FixedClock:
    def now(self) -> datetime:
        return FIXED_NOW


def caller_from(call: dict[str, Any]) -> ToolCaller:
    return call["caller"]
