from types import SimpleNamespace

from deeptrace.orchestration.budget import task_budget_reason, writer_token_reserve


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
