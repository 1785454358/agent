from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from deeptrace.orchestration.budget import elapsed_seconds, get_budget_reason


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


def test_total_runtime_deadline_still_triggers() -> None:
    now = datetime.now(UTC)
    settings = SimpleNamespace(
        max_fetched_pages=20,
        max_runtime_seconds=100,
        max_cost_usd=None,
    )
    state = {"started_at": (now - timedelta(seconds=101)).isoformat()}
    assert get_budget_reason(state, settings, now) == "time_budget"
