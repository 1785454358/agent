from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import asyncio

from deeptrace.observability import (
    GlobalBudget,
    elapsed_seconds,
    get_budget_reason,
)


def test_elapsed_seconds_is_non_negative() -> None:
    now = datetime.now(UTC)
    assert elapsed_seconds((now - timedelta(seconds=2)).isoformat(), now) == 2


def test_steps_and_token_usage_do_not_trigger_budget() -> None:
    settings = SimpleNamespace(
        max_fetched_pages=20,
        max_runtime_seconds=600,
        max_cost_usd=None,
    )
    now = datetime.now(UTC)
    state = {
        "started_at": now.isoformat(),
        "step_count": 999_999_999,
        "api_token_count": 999_999_999,
    }
    assert get_budget_reason(state, settings, now) is None


def test_total_runtime_does_not_stop_research() -> None:
    now = datetime.now(UTC)
    settings = SimpleNamespace(
        max_fetched_pages=20,
        max_runtime_seconds=100,
        max_cost_usd=None,
    )
    state = {"started_at": (now - timedelta(seconds=101)).isoformat()}
    assert get_budget_reason(state, settings, now) is None


def test_global_usage_and_elapsed_time_are_statistics_only():
    now = datetime.now(UTC)
    settings = SimpleNamespace(
        max_runtime_seconds=1, max_total_tokens=1, max_cost_usd=1
    )
    budget = GlobalBudget(settings, now - timedelta(days=1))
    asyncio.run(budget.record_usage(input_tokens=100000, cost_usd=100, now=now))
    assert budget.stop_reason(now) is None


def test_parallel_tool_claims_never_exceed_limit():
    async def run():
        budget = GlobalBudget(SimpleNamespace(max_tool_calls=2), datetime.now(UTC))
        granted = await asyncio.gather(*(budget.acquire_tool() for _ in range(8)))
        assert sum(granted) == 2
        assert budget.tool_calls == 2
        assert budget.reason == "tool_call_limit"

    asyncio.run(run())
