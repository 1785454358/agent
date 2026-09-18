from __future__ import annotations

import pytest
from pydantic import ValidationError

from deeptrace.domain import ResearchTopicOutcome, unfinished_plan_items


def test_plan_fields_default_to_complete_for_legacy_outcomes() -> None:
    outcome = ResearchTopicOutcome.model_validate(
        {"query": "q", "executed_steps": 0}
    )

    assert outcome.plan_total == 0
    assert outcome.plan_completed == 0
    assert outcome.unfinished_todos == []
    assert outcome.plan_complete is True


def test_open_todos_mark_the_plan_incomplete() -> None:
    outcome = ResearchTopicOutcome(
        query="q",
        executed_steps=1,
        plan_total=2,
        plan_completed=1,
        unfinished_todos=["尚未完成的步骤"],
    )

    assert outcome.plan_complete is False
    assert unfinished_plan_items([outcome]) == ["尚未完成的步骤"]


def test_plan_completed_cannot_exceed_total() -> None:
    with pytest.raises(ValidationError):
        ResearchTopicOutcome(
            query="q", executed_steps=0, plan_total=1, plan_completed=2
        )
