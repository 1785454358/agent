import asyncio

import pytest

from deeptrace.domain import ToolName, ToolResult
from deeptrace.tools.cache import (
    InMemorySuccessCache,
    SingleflightExecutionError,
    SuccessCacheSingleflight,
    page_cache_key,
    search_cache_key,
)


def _result(*, preview: str = "result", ok: bool = True) -> ToolResult:
    return ToolResult(
        request_id="request-1",
        run_id="run-1",
        thread_id="thread-1",
        call_id="call-1",
        tool=ToolName.SEARCH_WEB,
        ok=ok,
        error_code=None if ok else "provider_error",
        preview=preview if ok else "",
    )


def test_search_cache_keys_normalize_query_provider_and_options() -> None:
    first = search_cache_key(
        "  LangGraph   Harness ", " Tavily ", {"limit": 3, "lang": "en"}
    )
    reordered = search_cache_key(
        "langgraph harness", "tavily", {"lang": "en", "limit": 3}
    )

    assert first == reordered
    assert first != search_cache_key(
        "langgraph harness", "other", {"lang": "en", "limit": 3}
    )


def test_page_cache_keys_normalize_url_and_include_content_version() -> None:
    first = page_cache_key(
        "https://EXAMPLE.com/article/?utm_source=test", content_version="v1"
    )
    normalized = page_cache_key(
        "https://example.com/article", content_version="v1"
    )

    assert first == normalized
    assert first != page_cache_key(
        "https://example.com/article", content_version="v2"
    )


@pytest.mark.asyncio
async def test_cache_accepts_only_successful_results_and_returns_copies() -> None:
    cache = InMemorySuccessCache()
    key = search_cache_key("query", "provider", {})

    assert not await cache.put(key, _result(ok=False))
    assert await cache.get(key) is None
    assert await cache.put(key, _result(preview="stored"))
    first = await cache.get(key)
    second = await cache.get(key)

    assert first is not None
    assert second is not None
    first.preview = "mutated"
    assert second.preview == "stored"


@pytest.mark.asyncio
async def test_concurrent_miss_runs_factory_once_and_marks_followers_cached() -> None:
    coordinator = SuccessCacheSingleflight(InMemorySuccessCache())
    key = search_cache_key("query", "provider", {})
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def factory() -> ToolResult:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return _result()

    leader = asyncio.create_task(coordinator.get_or_execute(key, factory))
    await started.wait()
    follower = asyncio.create_task(coordinator.get_or_execute(key, factory))
    await asyncio.sleep(0)
    release.set()
    leader_result, follower_result = await asyncio.gather(leader, follower)

    assert calls == 1
    assert leader_result.cached is False
    assert follower_result.cached is True
    assert (await coordinator.get_or_execute(key, factory)).cached is True
    assert calls == 1


@pytest.mark.asyncio
async def test_cancelling_follower_does_not_cancel_shared_leader() -> None:
    coordinator = SuccessCacheSingleflight(InMemorySuccessCache())
    key = search_cache_key("query", "provider", {})
    started = asyncio.Event()
    release = asyncio.Event()

    async def factory() -> ToolResult:
        started.set()
        await release.wait()
        return _result()

    leader = asyncio.create_task(coordinator.get_or_execute(key, factory))
    await started.wait()
    follower = asyncio.create_task(coordinator.get_or_execute(key, factory))
    await asyncio.sleep(0)
    follower.cancel()
    with pytest.raises(asyncio.CancelledError):
        await follower

    assert not leader.done()
    release.set()
    assert (await leader).ok


@pytest.mark.asyncio
async def test_leader_failure_is_sanitized_for_followers_and_allows_retry() -> None:
    coordinator = SuccessCacheSingleflight(InMemorySuccessCache())
    key = search_cache_key("query", "provider", {})
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def failing_factory() -> ToolResult:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        raise RuntimeError("secret provider response")

    leader = asyncio.create_task(coordinator.get_or_execute(key, failing_factory))
    await started.wait()
    follower = asyncio.create_task(
        coordinator.get_or_execute(key, failing_factory)
    )
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(RuntimeError, match="secret provider response"):
        await leader
    with pytest.raises(SingleflightExecutionError, match="shared execution failed") as exc:
        await follower
    assert "secret" not in str(exc.value)

    async def succeeding_factory() -> ToolResult:
        nonlocal calls
        calls += 1
        return _result(preview="retry")

    assert (await coordinator.get_or_execute(key, succeeding_factory)).preview == "retry"
    assert calls == 2


@pytest.mark.asyncio
async def test_leader_cancellation_wakes_followers_and_allows_retry() -> None:
    coordinator = SuccessCacheSingleflight(InMemorySuccessCache())
    key = search_cache_key("query", "provider", {})
    started = asyncio.Event()

    async def blocked_factory() -> ToolResult:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    leader = asyncio.create_task(coordinator.get_or_execute(key, blocked_factory))
    await started.wait()
    follower = asyncio.create_task(coordinator.get_or_execute(key, blocked_factory))
    await asyncio.sleep(0)
    leader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leader
    with pytest.raises(SingleflightExecutionError, match="shared execution failed"):
        await asyncio.wait_for(follower, timeout=0.1)

    async def succeeding_factory() -> ToolResult:
        return _result(preview="after-cancel")

    recovered = await coordinator.get_or_execute(key, succeeding_factory)
    assert recovered.preview == "after-cancel"


@pytest.mark.asyncio
async def test_refresh_preserves_old_cache_until_a_new_success() -> None:
    cache = InMemorySuccessCache()
    coordinator = SuccessCacheSingleflight(cache)
    key = page_cache_key("https://example.com/page", content_version="current")
    await cache.put(key, _result(preview="old"))

    async def failed_refresh() -> ToolResult:
        return _result(ok=False)

    failed = await coordinator.get_or_execute(key, failed_refresh, refresh=True)
    assert not failed.ok
    assert (await cache.get(key)).preview == "old"  # type: ignore[union-attr]

    async def successful_refresh() -> ToolResult:
        return _result(preview="new")

    refreshed = await coordinator.get_or_execute(
        key, successful_refresh, refresh=True
    )
    assert refreshed.preview == "new"
    assert refreshed.cached is False
    assert (await coordinator.get_or_execute(key, successful_refresh)).preview == "new"
