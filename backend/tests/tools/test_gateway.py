from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, Field

from deeptrace.domain import ResearchMode, ToolName, ToolRequest
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.execution_ledger import SqlAlchemyToolExecutionStore
from deeptrace.persistence.orm import Base
from deeptrace.tools.budget import BudgetScopeKey, BudgetUnits, InMemoryBudgetManager
from deeptrace.tools.cache import InMemorySuccessCache, SuccessCacheSingleflight
from deeptrace.tools.contracts import CachePolicy, ToolCapability, ToolSpec
from deeptrace.tools.evidence_store import EvidenceDraft, InMemoryEvidenceStore
from deeptrace.tools.execution_store import InMemoryToolExecutionStore
from deeptrace.tools.gateway import AgentToolGateway, ToolAdapterResult
from deeptrace.tools.policy import (
    CallerRole,
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
    ToolCaller,
    UrlAuthorization,
    UrlAuthorizationSource,
)
from deeptrace.tools.registry import ToolRegistry


class SearchArguments(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=3, ge=1, le=10)


class FetchArguments(BaseModel):
    url: str = Field(min_length=1)


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def emit(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, payload))


class FailingEventSink:
    async def emit(self, event_type: str, payload: dict[str, object]) -> None:
        raise RuntimeError("telemetry-secret")


class FailingCacheCoordinator:
    async def get_or_execute(self, *args, **kwargs):
        raise RuntimeError("cache-secret")


def _request(
    *,
    call_id: str = "call-1",
    tool: ToolName = ToolName.SEARCH_WEB,
    arguments: dict[str, object] | None = None,
) -> ToolRequest:
    return ToolRequest(
        request_id="request-1",
        run_id="run-1",
        thread_id="thread-1",
        call_id=call_id,
        tool=tool,
        arguments=arguments or {"query": "LangGraph harness"},
    )


def _caller(
    role: CallerRole = CallerRole.WORKFLOW_GRAPH,
) -> ToolCaller:
    mode = (
        ResearchMode.MULTI_AGENT
        if role is CallerRole.MULTI_AGENT_SUPERVISOR
        else ResearchMode.WORKFLOW
    )
    return ToolCaller(caller_id="researcher", role=role, mode=mode)


def _budget() -> InMemoryBudgetManager:
    limit = BudgetUnits(tool_calls=10, network_requests=10, fetched_pages=10)
    return InMemoryBudgetManager(
        {
            BudgetScopeKey.for_run("run-1"): limit,
            BudgetScopeKey.for_mode("run-1", ResearchMode.WORKFLOW): limit,
            BudgetScopeKey.for_agent(
                "run-1", ResearchMode.WORKFLOW, "researcher"
            ): limit,
            BudgetScopeKey.for_mode("run-1", ResearchMode.MULTI_AGENT): limit,
            BudgetScopeKey.for_agent(
                "run-1", ResearchMode.MULTI_AGENT, "researcher"
            ): limit,
        }
    )


def _gateway(
    spec: ToolSpec,
    *,
    budget: InMemoryBudgetManager | None = None,
    events: RecordingEventSink | None = None,
    evidence: InMemoryEvidenceStore | None = None,
    executions=None,
) -> tuple[AgentToolGateway, InMemoryBudgetManager, RecordingEventSink, InMemoryEvidenceStore]:
    registry = ToolRegistry()
    registry.register(spec)
    budget = budget or _budget()
    events = events or RecordingEventSink()
    evidence = evidence or InMemoryEvidenceStore()
    gateway = AgentToolGateway(
        registry=registry,
        allowlist=StaticToolAllowlist(),
        security=DeterministicUrlSecurityPolicy(),
        budgets=budget,
        executions=executions or InMemoryToolExecutionStore(),
        cache=SuccessCacheSingleflight(InMemorySuccessCache()),
        evidence_store=evidence,
        event_sink=events,
    )
    return gateway, budget, events, evidence


@pytest.mark.asyncio
async def test_non_cached_execution_persists_committed_budget_units(tmp_path) -> None:
    async def handler(_arguments: BaseModel) -> ToolAdapterResult:
        return ToolAdapterResult(preview="answer")

    database = (tmp_path / "gateway-ledger.db").as_posix()
    engine, sessions = create_session_factory(f"sqlite+aiosqlite:///{database}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    ledger = SqlAlchemyToolExecutionStore(sessions)
    gateway, _budget, _events, _evidence = _gateway(
        _spec(handler), executions=ledger
    )
    try:
        result = await gateway.execute(
            tenant_id="tenant-a", caller=_caller(), request=_request()
        )
        usage = await ledger.tool_usage_for_run("run-1")
    finally:
        await engine.dispose()

    assert result.ok
    assert usage == {
        ("workflow", "researcher"): BudgetUnits(
            tool_calls=1, network_requests=1
        )
    }


def _spec(
    handler,
    *,
    tool: ToolName = ToolName.SEARCH_WEB,
    timeout: float = 1.0,
    preview_limit: int = 100,
    stores_evidence: bool = False,
) -> ToolSpec:
    return ToolSpec(
        name=tool,
        argument_model=(FetchArguments if tool is ToolName.FETCH_PAGE else SearchArguments),
        handler=handler,
        capability=(
            ToolCapability.PAGE_FETCH
            if tool is ToolName.FETCH_PAGE
            else ToolCapability.WEB_SEARCH
        ),
        cache_policy=CachePolicy.SUCCESS,
        timeout_seconds=timeout,
        preview_limit=preview_limit,
        stores_evidence=stores_evidence,
    )


@pytest.mark.asyncio
async def test_rejections_happen_before_budget_and_execution_events() -> None:
    calls = 0

    async def handler(_arguments: BaseModel) -> ToolAdapterResult:
        nonlocal calls
        calls += 1
        return ToolAdapterResult(preview="unused")

    gateway, budget, events, _evidence = _gateway(_spec(handler))

    invalid = await gateway.execute(
        tenant_id="tenant-a",
        caller=_caller(),
        request=_request(arguments={"query": ""}),
    )
    denied = await gateway.execute(
        tenant_id="tenant-a",
        caller=_caller(CallerRole.MULTI_AGENT_SUPERVISOR),
        request=_request(call_id="call-2"),
    )

    assert invalid.error_code == "invalid_arguments"
    assert denied.error_code == "tool_not_allowed"
    assert calls == 0
    assert events.events == []
    snapshot = await budget.snapshot()
    assert snapshot.for_scope(BudgetScopeKey.for_run("run-1")).used.is_empty()
    assert snapshot.for_scope(BudgetScopeKey.for_run("run-1")).reserved.is_empty()


@pytest.mark.asyncio
async def test_same_call_replays_without_provider_or_budget_charge() -> None:
    calls = 0

    async def handler(_arguments: BaseModel) -> ToolAdapterResult:
        nonlocal calls
        calls += 1
        return ToolAdapterResult(preview="answer")

    gateway, budget, events, _evidence = _gateway(_spec(handler))
    request = _request()

    first = await gateway.execute(tenant_id="tenant-a", caller=_caller(), request=request)
    replay = await gateway.execute(tenant_id="tenant-a", caller=_caller(), request=request)

    assert first.ok and not first.replayed
    assert replay.ok and replay.replayed
    assert calls == 1
    run = (await budget.snapshot()).for_scope(BudgetScopeKey.for_run("run-1"))
    assert run.used == BudgetUnits(tool_calls=1, network_requests=1)
    assert [name for name, _payload in events.events] == [
        "tool.started",
        "tool.completed",
    ]


@pytest.mark.asyncio
async def test_different_calls_share_provider_but_keep_their_own_correlation() -> None:
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_arguments: BaseModel) -> ToolAdapterResult:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return ToolAdapterResult(preview="shared")

    gateway, budget, _events, _evidence = _gateway(_spec(handler))
    leader_task = asyncio.create_task(
        gateway.execute(tenant_id="tenant-a", caller=_caller(), request=_request())
    )
    await started.wait()
    follower_task = asyncio.create_task(
        gateway.execute(
            tenant_id="tenant-a", caller=_caller(), request=_request(call_id="call-2")
        )
    )
    await asyncio.sleep(0)
    release.set()
    leader, follower = await asyncio.gather(leader_task, follower_task)

    assert calls == 1
    assert leader.call_id == "call-1" and not leader.cached
    assert follower.call_id == "call-2" and follower.cached
    run = (await budget.snapshot()).for_scope(BudgetScopeKey.for_run("run-1"))
    assert run.used == BudgetUnits(tool_calls=1, network_requests=1)
    assert run.reserved.is_empty()


@pytest.mark.asyncio
async def test_page_body_is_stored_as_evidence_and_only_preview_enters_result() -> None:
    body = "正文" * 100

    async def handler(arguments: FetchArguments) -> ToolAdapterResult:
        return ToolAdapterResult(
            preview=body,
            evidence=EvidenceDraft(
                canonical_url=arguments.url,
                title="Source",
                media_type="text/html",
                body=body,
                fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
                source_quality=0.8,
            ),
        )

    gateway, _budget_manager, _events, evidence = _gateway(
        _spec(
            handler,
            tool=ToolName.FETCH_PAGE,
            preview_limit=20,
            stores_evidence=True,
        )
    )
    url = "https://example.com/article"
    result = await gateway.execute(
        tenant_id="tenant-a",
        caller=_caller(),
        request=_request(tool=ToolName.FETCH_PAGE, arguments={"url": url}),
        authorization=UrlAuthorization(
            source=UrlAuthorizationSource.SEARCH_RESULT,
            urls=frozenset({url}),
        ),
    )

    assert result.ok
    assert len(result.preview) == 20
    assert len(result.evidence_ids) == 1
    assert result.data_ref == f"evidence://{result.evidence_ids[0]}/body"
    assert await evidence.read_body("tenant-a", result.evidence_ids[0]) == body
    assert body not in result.model_dump_json()


@pytest.mark.asyncio
async def test_timeout_is_sanitized_recorded_and_charged() -> None:
    async def handler(_arguments: BaseModel) -> ToolAdapterResult:
        await asyncio.sleep(1)
        return ToolAdapterResult(preview="secret-token")

    gateway, budget, events, _evidence = _gateway(_spec(handler, timeout=0.01))

    result = await gateway.execute(
        tenant_id="tenant-a", caller=_caller(), request=_request()
    )

    assert not result.ok and result.error_code == "provider_timeout"
    assert "secret" not in result.model_dump_json()
    assert "secret" not in str(events.events)
    run = (await budget.snapshot()).for_scope(BudgetScopeKey.for_run("run-1"))
    assert run.used == BudgetUnits(tool_calls=1, network_requests=1)
    assert [name for name, _payload in events.events] == [
        "tool.started",
        "tool.completed",
    ]
    completed = events.events[-1][1]
    assert completed["error_code"] == "provider_timeout"
    assert completed["cached"] is False
    assert completed["replayed"] is False
    assert completed["budget_delta"] == {
        "model_calls": 0,
        "tool_calls": 1,
        "network_requests": 1,
        "fetched_pages": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "rounds": 0,
    }


@pytest.mark.asyncio
async def test_cancellation_releases_budget_and_same_call_can_be_reclaimed() -> None:
    calls = 0
    started = asyncio.Event()

    async def handler(_arguments: BaseModel) -> ToolAdapterResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.Event().wait()
        return ToolAdapterResult(preview="recovered")

    gateway, budget, events, _evidence = _gateway(_spec(handler))
    request = _request()
    cancelled = asyncio.create_task(
        gateway.execute(tenant_id="tenant-a", caller=_caller(), request=request)
    )
    await started.wait()
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    after_cancel = (await budget.snapshot()).for_scope(
        BudgetScopeKey.for_run("run-1")
    )
    assert after_cancel.used.is_empty()
    assert after_cancel.reserved.is_empty()
    assert [name for name, _payload in events.events] == [
        "tool.started",
        "tool.cancelled",
    ]

    recovered = await gateway.execute(
        tenant_id="tenant-a", caller=_caller(), request=request
    )

    assert recovered.ok and recovered.preview == "recovered"
    assert calls == 2
    run = (await budget.snapshot()).for_scope(BudgetScopeKey.for_run("run-1"))
    assert run.used == BudgetUnits(tool_calls=1, network_requests=1)
    assert run.reserved.is_empty()


@pytest.mark.asyncio
async def test_success_cache_is_isolated_by_tenant_for_evidence_references() -> None:
    calls = 0
    url = "https://example.com/article"

    async def handler(arguments: FetchArguments) -> ToolAdapterResult:
        nonlocal calls
        calls += 1
        return ToolAdapterResult(
            preview="page",
            evidence=EvidenceDraft(
                canonical_url=arguments.url,
                title="Source",
                media_type="text/html",
                body=f"tenant execution {calls}",
                fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
                source_quality=0.8,
            ),
        )

    gateway, _budget_manager, _events, evidence = _gateway(
        _spec(handler, tool=ToolName.FETCH_PAGE, stores_evidence=True)
    )
    authorization = UrlAuthorization(
        source=UrlAuthorizationSource.SEARCH_RESULT,
        urls=frozenset({url}),
    )

    tenant_a = await gateway.execute(
        tenant_id="tenant-a",
        caller=_caller(),
        request=_request(tool=ToolName.FETCH_PAGE, arguments={"url": url}),
        authorization=authorization,
    )
    tenant_b = await gateway.execute(
        tenant_id="tenant-b",
        caller=_caller(),
        request=_request(tool=ToolName.FETCH_PAGE, arguments={"url": url}),
        authorization=authorization,
    )

    assert calls == 2
    assert await evidence.read_body("tenant-a", tenant_a.evidence_ids[0]) == (
        "tenant execution 1"
    )
    assert await evidence.read_body("tenant-b", tenant_b.evidence_ids[0]) == (
        "tenant execution 2"
    )


@pytest.mark.asyncio
async def test_telemetry_failure_does_not_change_tool_outcome() -> None:
    calls = 0

    async def handler(_arguments: BaseModel) -> ToolAdapterResult:
        nonlocal calls
        calls += 1
        return ToolAdapterResult(preview="answer")

    registry = ToolRegistry()
    registry.register(_spec(handler))
    gateway = AgentToolGateway(
        registry=registry,
        allowlist=StaticToolAllowlist(),
        security=DeterministicUrlSecurityPolicy(),
        budgets=_budget(),
        executions=InMemoryToolExecutionStore(),
        cache=SuccessCacheSingleflight(InMemorySuccessCache()),
        evidence_store=InMemoryEvidenceStore(),
        event_sink=FailingEventSink(),
    )

    result = await gateway.execute(
        tenant_id="tenant-a", caller=_caller(), request=_request()
    )

    assert result.ok and result.preview == "answer"
    assert calls == 1


@pytest.mark.asyncio
async def test_cache_infrastructure_failure_does_not_consume_network_budget() -> None:
    calls = 0

    async def handler(_arguments: BaseModel) -> ToolAdapterResult:
        nonlocal calls
        calls += 1
        return ToolAdapterResult(preview="unused")

    registry = ToolRegistry()
    registry.register(_spec(handler))
    budget = _budget()
    gateway = AgentToolGateway(
        registry=registry,
        allowlist=StaticToolAllowlist(),
        security=DeterministicUrlSecurityPolicy(),
        budgets=budget,
        executions=InMemoryToolExecutionStore(),
        cache=FailingCacheCoordinator(),
        evidence_store=InMemoryEvidenceStore(),
        event_sink=RecordingEventSink(),
    )

    result = await gateway.execute(
        tenant_id="tenant-a", caller=_caller(), request=_request()
    )

    assert not result.ok and result.error_code == "tool_internal_error"
    assert "secret" not in result.model_dump_json()
    assert calls == 0
    run = (await budget.snapshot()).for_scope(BudgetScopeKey.for_run("run-1"))
    assert run.used.is_empty()
    assert run.reserved.is_empty()
