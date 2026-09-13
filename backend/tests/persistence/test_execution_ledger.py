from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from deeptrace.domain import ToolName, ToolRequest, ToolResult
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.execution_ledger import SqlAlchemyToolExecutionStore
from deeptrace.persistence.orm import Base
from deeptrace.tools.budget import BudgetUnits
from deeptrace.tools.execution_store import ClaimDisposition, ExecutionAbandonedError


def _request(call_id: str = "call-1") -> ToolRequest:
    return ToolRequest(
        request_id="request-1",
        run_id="run-1",
        thread_id="thread-1",
        call_id=call_id,
        tool=ToolName.SEARCH_WEB,
        arguments={"query": "LangGraph harness"},
    )


def _result(request: ToolRequest, *, error_code: str | None = None) -> ToolResult:
    return ToolResult(
        request_id=request.request_id,
        run_id=request.run_id,
        thread_id=request.thread_id,
        call_id=request.call_id,
        tool=request.tool,
        ok=error_code is None,
        error_code=error_code,
        preview="answer" if error_code is None else "",
    )


@pytest_asyncio.fixture
async def sql_store(tmp_path):
    database = (tmp_path / "execution-ledger.db").as_posix()
    engine, sessions = create_session_factory(f"sqlite+aiosqlite:///{database}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield SqlAlchemyToolExecutionStore(
        sessions, poll_interval_seconds=0.001, max_polls=100
    )
    await engine.dispose()


@pytest.mark.asyncio
async def test_recoverable_owner_wakes_follower_and_next_claim_retries(sql_store) -> None:
    request = _request()
    owner = await sql_store.claim(
        "tenant-a", request, mode="workflow", caller_id="researcher"
    )
    follower = await sql_store.claim(
        "tenant-a", request, mode="workflow", caller_id="researcher"
    )
    waiting = asyncio.create_task(sql_store.wait(follower))
    await asyncio.sleep(0)

    assert await sql_store.complete(owner, _result(request, error_code="provider_timeout"))
    with pytest.raises(ExecutionAbandonedError):
        await waiting

    replacement = await sql_store.claim(
        "tenant-a", request, mode="workflow", caller_id="researcher"
    )
    assert replacement.disposition is ClaimDisposition.OWNER
    assert replacement.generation == 2


@pytest.mark.asyncio
async def test_usage_accumulates_actual_units_across_retry_generations(sql_store) -> None:
    request = _request()
    owner = await sql_store.claim(
        "tenant-a", request, mode="workflow", caller_id="researcher"
    )
    search_units = BudgetUnits(tool_calls=1, network_requests=1)
    assert await sql_store.complete(
        owner,
        _result(request, error_code="provider_timeout"),
        consumed=search_units,
    )
    replacement = await sql_store.claim(
        "tenant-a", request, mode="workflow", caller_id="researcher"
    )
    assert await sql_store.complete(
        replacement, _result(request), consumed=search_units
    )

    cached_request = _request("call-cached")
    cached_owner = await sql_store.claim(
        "tenant-a", cached_request, mode="workflow", caller_id="researcher"
    )
    assert await sql_store.complete(
        cached_owner, _result(cached_request), consumed=BudgetUnits()
    )

    assert await sql_store.tool_usage_for_run("run-1") == {
        ("workflow", "researcher"): BudgetUnits(
            tool_calls=2, network_requests=2
        )
    }


@pytest.mark.asyncio
async def test_concurrent_first_claims_resolve_to_one_owner_and_one_follower(
    sql_store,
) -> None:
    request = _request()
    start = asyncio.Event()

    async def claim():
        await start.wait()
        return await sql_store.claim(
            "tenant-a", request, mode="workflow", caller_id="researcher"
        )

    tasks = [asyncio.create_task(claim()) for _ in range(2)]
    start.set()
    claims = await asyncio.gather(*tasks)

    assert sorted(item.disposition for item in claims) == [
        ClaimDisposition.FOLLOWER,
        ClaimDisposition.OWNER,
    ]


@pytest.mark.asyncio
async def test_repeated_completion_is_idempotent_for_durable_usage(sql_store) -> None:
    request = _request()
    owner = await sql_store.claim(
        "tenant-a", request, mode="workflow", caller_id="researcher"
    )
    units = BudgetUnits(tool_calls=1, network_requests=1)

    assert await sql_store.complete(owner, _result(request), consumed=units)
    assert not await sql_store.complete(owner, _result(request), consumed=units)

    assert await sql_store.tool_usage_for_run("run-1") == {
        ("workflow", "researcher"): units
    }
