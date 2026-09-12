import asyncio

import pytest

from deeptrace.domain import ToolName, ToolRequest, ToolResult
from deeptrace.tools.execution_store import (
    ClaimDisposition,
    ExecutionAbandonedError,
    ExecutionConflictError,
    InMemoryToolExecutionStore,
    canonical_request_fingerprint,
)


def _request(*, call_id: str = "call-1", query: str = "LangGraph") -> ToolRequest:
    return ToolRequest(
        request_id="request-1",
        run_id="run-1",
        thread_id="thread-1",
        call_id=call_id,
        tool=ToolName.SEARCH_WEB,
        arguments={"query": query, "options": {"limit": 3, "language": "en"}},
    )


def _result(request: ToolRequest, *, ok: bool = True) -> ToolResult:
    return ToolResult(
        request_id=request.request_id,
        run_id=request.run_id,
        thread_id=request.thread_id,
        call_id=request.call_id,
        tool=request.tool,
        ok=ok,
        error_code=None if ok else "provider_error",
        preview="result" if ok else "",
    )


def test_request_fingerprint_is_canonical_and_content_sensitive() -> None:
    first = _request()
    reordered = first.model_copy(
        update={
            "arguments": {
                "options": {"language": "en", "limit": 3},
                "query": "LangGraph",
            }
        }
    )

    assert canonical_request_fingerprint(first) == canonical_request_fingerprint(
        reordered
    )
    assert canonical_request_fingerprint(first) != canonical_request_fingerprint(
        _request(query="Agent Harness")
    )
    assert canonical_request_fingerprint(first) != canonical_request_fingerprint(
        first.model_copy(update={"thread_id": "thread-2"})
    )


@pytest.mark.asyncio
async def test_first_claim_owns_followers_wait_and_later_claims_replay() -> None:
    store = InMemoryToolExecutionStore()
    request = _request()

    owner = await store.claim("tenant-a", request)
    follower = await store.claim("tenant-a", request)

    assert owner.disposition is ClaimDisposition.OWNER
    assert follower.disposition is ClaimDisposition.FOLLOWER
    waiting = asyncio.create_task(store.wait(follower))
    await asyncio.sleep(0)
    expected = _result(request)
    assert await store.complete(owner, expected)
    assert await waiting == expected

    replay = await store.claim("tenant-a", request)
    assert replay.disposition is ClaimDisposition.REPLAY
    assert replay.result == expected


@pytest.mark.asyncio
async def test_cancelling_follower_does_not_cancel_owner_or_terminal_result() -> None:
    store = InMemoryToolExecutionStore()
    request = _request()
    owner = await store.claim("tenant-a", request)
    follower = await store.claim("tenant-a", request)
    waiting = asyncio.create_task(store.wait(follower))
    await asyncio.sleep(0)

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    expected = _result(request)
    assert await store.complete(owner, expected)
    replay = await store.claim("tenant-a", request)
    assert replay.result == expected


@pytest.mark.asyncio
async def test_call_id_reuse_with_different_fingerprint_is_a_conflict() -> None:
    store = InMemoryToolExecutionStore()
    await store.claim("tenant-a", _request(query="first"))

    with pytest.raises(ExecutionConflictError, match="different fingerprint"):
        await store.claim("tenant-a", _request(query="second"))


@pytest.mark.asyncio
async def test_failed_provider_result_is_terminal_and_replayed() -> None:
    store = InMemoryToolExecutionStore()
    request = _request()
    owner = await store.claim("tenant-a", request)
    failure = _result(request, ok=False)

    assert await store.complete(owner, failure)
    replay = await store.claim("tenant-a", request)

    assert replay.disposition is ClaimDisposition.REPLAY
    assert replay.result == failure


@pytest.mark.asyncio
async def test_abandoned_owner_wakes_followers_and_allows_explicit_reclaim() -> None:
    store = InMemoryToolExecutionStore()
    request = _request()
    owner = await store.claim("tenant-a", request)
    follower = await store.claim("tenant-a", request)

    assert await store.abandon(owner)
    with pytest.raises(ExecutionAbandonedError, match="execution was abandoned"):
        await store.wait(follower)

    replacement = await store.claim("tenant-a", request)
    assert replacement.disposition is ClaimDisposition.OWNER
    assert replacement.owner_token != owner.owner_token
    assert await store.complete(replacement, _result(request))


@pytest.mark.asyncio
async def test_claims_are_isolated_by_tenant_and_owner_actions_are_idempotent() -> None:
    store = InMemoryToolExecutionStore()
    request = _request()
    first = await store.claim("tenant-a", request)
    second = await store.claim("tenant-b", request)

    assert first.disposition is ClaimDisposition.OWNER
    assert second.disposition is ClaimDisposition.OWNER
    result = _result(request)
    assert await store.complete(first, result)
    assert not await store.complete(first, result)
    assert not await store.abandon(first)
