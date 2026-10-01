from __future__ import annotations

import pytest
from pydantic import ValidationError

from deeptrace.domain import (
    ResearchMode,
    ResearchTopicInput,
    ResearchTopicOutcome,
    TopicStepError,
    unfinished_plan_items,
)
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer


def test_plan_fields_default_to_complete_for_legacy_outcomes() -> None:
    outcome = ResearchTopicOutcome.model_validate({"query": "q", "executed_steps": 0})

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


def _topic_input(**overrides: object) -> ResearchTopicInput:
    values: dict[str, object] = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "query": "LangGraph harness",
        "max_pages": 3,
        "mode": ResearchMode.WORKFLOW,
        "caller_id": "workflow-graph",
    }
    values.update(overrides)
    return ResearchTopicInput(**values)


def test_research_topic_input_is_bounded_and_canonical() -> None:
    topic_input = _topic_input()
    assert topic_input.max_pages == 3
    assert topic_input.mode is ResearchMode.WORKFLOW

    with pytest.raises(ValidationError):
        _topic_input(query="   ")
    with pytest.raises(ValidationError):
        _topic_input(query="q" * 1_001)
    with pytest.raises(ValidationError):
        _topic_input(max_pages=0)
    with pytest.raises(ValidationError):
        _topic_input(max_pages=9)
    with pytest.raises(ValidationError):
        _topic_input(run_id="")
    with pytest.raises(ValidationError):
        _topic_input(unexpected="value")


def test_topic_outcome_rejects_duplicate_references() -> None:
    with pytest.raises(ValidationError, match="evidence_ids must be unique"):
        ResearchTopicOutcome(
            query="q",
            evidence_ids=["evidence-1", "evidence-1"],
            attempted_urls=["https://example.com/a"],
            errors=[],
            executed_steps=2,
        )
    with pytest.raises(ValidationError, match="attempted_urls must be unique"):
        ResearchTopicOutcome(
            query="q",
            evidence_ids=["evidence-1"],
            attempted_urls=[
                "https://example.com/a",
                "https://example.com/a",
            ],
            errors=[],
            executed_steps=2,
        )


def test_topic_step_errors_are_bounded_and_stable() -> None:
    error = TopicStepError(
        stage="fetch", target="https://example.com/a", code="empty_page"
    )
    assert error.target == "https://example.com/a"
    with pytest.raises(ValidationError):
        TopicStepError(stage="plan", target="", code="nope")
    with pytest.raises(ValidationError):
        TopicStepError(stage="fetch", target="u" * 3_000, code="empty_page")
    with pytest.raises(ValidationError):
        TopicStepError(stage="fetch", target="https://example.com/a", code="")


def test_topic_contracts_round_trip_through_strict_serializer() -> None:
    state = {
        "topic_input": _topic_input(),
        "outcome": ResearchTopicOutcome(
            query="LangGraph harness",
            evidence_ids=["evidence-1"],
            attempted_urls=["https://example.com/a"],
            errors=[
                TopicStepError(
                    stage="fetch", target="https://example.com/b", code="empty_page"
                )
            ],
            executed_steps=3,
        ),
    }
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(state))

    assert restored == state
    assert isinstance(restored["topic_input"], ResearchTopicInput)
    assert isinstance(restored["outcome"], ResearchTopicOutcome)
    assert isinstance(restored["outcome"].errors[0], TopicStepError)
