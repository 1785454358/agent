from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from deeptrace.domain import ResearchMode, ToolName, ToolRequest
from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.tools import AgentToolGateway, build_research_tool_registry
from deeptrace.tools.budget import BudgetScopeKey, BudgetUnits, InMemoryBudgetManager
from deeptrace.tools.cache import InMemorySuccessCache, SuccessCacheSingleflight
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from deeptrace.tools.execution_store import InMemoryToolExecutionStore
from deeptrace.tools.policy import (
    CallerRole,
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
    ToolCaller,
    UrlAuthorization,
    UrlAuthorizationSource,
)


class EventSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class Fetcher:
    def __init__(self, body: str) -> None:
        self.body = body
        self.calls = 0

    async def fetch(self, url: str) -> RawDocument:
        self.calls += 1
        return RawDocument(
            doc_id="doc-1",
            requested_url=url,
            final_url=url,
            canonical_url=url,
            title="Harness source",
            content=self.body,
            content_hash="hash-1",
            fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
            scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
            status="success",
        )


def _request(call_id: str, tool: ToolName, arguments: dict) -> ToolRequest:
    return ToolRequest(
        request_id="request-1",
        run_id="run-1",
        thread_id="thread-1",
        call_id=call_id,
        tool=tool,
        arguments=arguments,
    )


@pytest.mark.asyncio
async def test_unified_gateway_exit_gate() -> None:
    search_calls = 0
    search_started = asyncio.Event()
    release_search = asyncio.Event()

    async def search(_query: str) -> dict:
        nonlocal search_calls
        search_calls += 1
        search_started.set()
        await release_search.wait()
        return {
            "ok": True,
            "results": [
                {
                    "url": "https://example.com/article",
                    "title": "Source",
                    "content": "candidate",
                }
            ],
        }

    fetcher = Fetcher("large evidence body " * 1_000)
    registry = build_research_tool_registry(
        search=search,
        fetcher=fetcher,
        memory=None,
    )
    run_scope = BudgetScopeKey.for_run("run-1")
    mode_scope = BudgetScopeKey.for_mode("run-1", ResearchMode.WORKFLOW)
    agent_scope = BudgetScopeKey.for_agent(
        "run-1", ResearchMode.WORKFLOW, "researcher"
    )
    limit = BudgetUnits(tool_calls=10, network_requests=10, fetched_pages=10)
    budgets = InMemoryBudgetManager(
        {run_scope: limit, mode_scope: limit, agent_scope: limit}
    )
    evidence = InMemoryEvidenceStore()
    events = EventSink()
    gateway = AgentToolGateway(
        registry=registry,
        allowlist=StaticToolAllowlist(),
        security=DeterministicUrlSecurityPolicy(),
        budgets=budgets,
        executions=InMemoryToolExecutionStore(),
        cache=SuccessCacheSingleflight(InMemorySuccessCache()),
        evidence_store=evidence,
        event_sink=events,
    )
    caller = ToolCaller(
        caller_id="researcher",
        role=CallerRole.WORKFLOW_GRAPH,
        mode=ResearchMode.WORKFLOW,
    )
    supervisor = ToolCaller(
        caller_id="supervisor",
        role=CallerRole.MULTI_AGENT_SUPERVISOR,
        mode=ResearchMode.MULTI_AGENT,
    )

    malformed = await gateway.execute(
        tenant_id="tenant-a",
        caller=caller,
        request=_request("invalid", ToolName.SEARCH_WEB, {"query": ""}),
    )
    denied = await gateway.execute(
        tenant_id="tenant-a",
        caller=supervisor,
        request=_request("denied", ToolName.SEARCH_WEB, {"query": "harness"}),
    )
    first_request = _request(
        "search-1", ToolName.SEARCH_WEB, {"query": "harness"}
    )
    first_task = asyncio.create_task(
        gateway.execute(tenant_id="tenant-a", caller=caller, request=first_request)
    )
    await search_started.wait()
    second_task = asyncio.create_task(
        gateway.execute(
            tenant_id="tenant-a",
            caller=caller,
            request=_request(
                "search-2", ToolName.SEARCH_WEB, {"query": "harness"}
            ),
        )
    )
    await asyncio.sleep(0)
    release_search.set()
    first, second = await asyncio.gather(first_task, second_task)
    replay = await gateway.execute(
        tenant_id="tenant-a", caller=caller, request=first_request
    )
    page = await gateway.execute(
        tenant_id="tenant-a",
        caller=caller,
        request=_request(
            "fetch-1",
            ToolName.FETCH_PAGE,
            {"url": "https://example.com/article"},
        ),
        authorization=UrlAuthorization(
            source=UrlAuthorizationSource.SEARCH_RESULT,
            urls=frozenset({"https://example.com/article"}),
        ),
    )

    assert registry.names() == tuple(ToolName)
    assert malformed.error_code == "invalid_arguments"
    assert denied.error_code == "tool_not_allowed"
    assert search_calls == 1
    assert first.ok and second.ok and second.cached
    assert replay.replayed and search_calls == 1
    assert fetcher.calls == 1 and page.ok
    assert len(page.preview) <= 1_000
    assert "large evidence body" not in page.preview
    assert await evidence.read_body("tenant-a", page.evidence_ids[0]) == fetcher.body
    run_budget = (await budgets.snapshot()).for_scope(run_scope)
    assert run_budget.used == BudgetUnits(
        tool_calls=2,
        network_requests=2,
        fetched_pages=1,
    )
    assert run_budget.reserved.is_empty()
    assert all("large evidence body" not in str(event) for event in events.events)
