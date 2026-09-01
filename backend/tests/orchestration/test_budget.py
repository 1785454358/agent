from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from deeptrace.orchestration.budget import (
    regular_research_deadline_reached,
    task_budget_reason,
    task_token_allowance,
    verification_token_reserve,
    writer_token_reserve,
)


def test_writer_reserve_and_task_limit(task_coverage) -> None:
    settings = SimpleNamespace(
        max_api_tokens=100_000,
        writer_token_reserve_ratio=0.15,
    )
    reserve = writer_token_reserve(settings)
    limited = task_coverage.model_copy(
        update={"api_token_budget": 100, "api_tokens_used": 100}
    )

    assert reserve == int(settings.max_api_tokens * 0.15)
    assert task_budget_reason(limited) == "task_token_budget"


def test_task_allowance_reserves_verifier_and_writer(research_plan) -> None:
    settings = SimpleNamespace(
        max_api_tokens=100_000,
        writer_token_reserve_ratio=0.15,
        verification_token_reserve_ratio=0.20,
    )
    state = {
        "research_plan": research_plan,
        "current_task_index": 0,
        "api_token_count": 0,
    }
    expected_pool = (
        settings.max_api_tokens
        - writer_token_reserve(settings)
        - verification_token_reserve(settings)
    )

    assert task_token_allowance(state, settings) == (
        expected_pool // len(research_plan.tasks)
    )


def test_regular_research_uses_early_runtime_deadline() -> None:
    now = datetime.now(UTC)
    settings = SimpleNamespace(
        max_runtime_seconds=100,
        research_runtime_ratio=0.70,
    )
    state = {"started_at": (now - timedelta(seconds=71)).isoformat()}

    assert regular_research_deadline_reached(state, settings, now)
