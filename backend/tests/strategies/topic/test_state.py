import pytest
from pydantic import ValidationError

from deeptrace.domain import (
    ResearchMode,
    ResearchTopicInput,
    ResearchTopicOutcome,
    TopicStepError,
)
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.topic.state import (
    FetchBranchState,
    ResearchTopicState,
    add_executed_steps,
    merge_topic_errors,
    merge_unique_evidence_ids,
    merge_unique_urls,
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
    error = TopicStepError(stage="fetch", target="https://example.com/a", code="empty_page")
    assert error.target == "https://example.com/a"
    with pytest.raises(ValidationError):
        TopicStepError(stage="plan", target="", code="nope")
    with pytest.raises(ValidationError):
        TopicStepError(stage="fetch", target="u" * 3_000, code="empty_page")
    with pytest.raises(ValidationError):
        TopicStepError(stage="fetch", target="https://example.com/a", code="")


def test_reducers_stably_dedupe_ids_and_merge_errors() -> None:
    assert merge_unique_evidence_ids([], ["evidence-2", "evidence-1"]) == [
        "evidence-2",
        "evidence-1",
    ]
    assert merge_unique_evidence_ids(["evidence-1"], ["evidence-1", "evidence-2"]) == [
        "evidence-1",
        "evidence-2",
    ]
    assert merge_unique_urls(None, ["https://example.com/a"]) == [
        "https://example.com/a"
    ]
    assert merge_unique_urls(["https://example.com/a"], ["https://example.com/a"]) == [
        "https://example.com/a"
    ]

    first = TopicStepError(stage="search", target="", code="search_failed")
    second = TopicStepError(stage="fetch", target="https://example.com/a", code="empty_page")
    assert merge_topic_errors(None, [first]) == [first]
    assert merge_topic_errors([first], [second]) == [first, second]
    assert merge_topic_errors([first], []) == [first]


def test_executed_steps_reducer_is_additive_and_replay_safe() -> None:
    assert add_executed_steps(None, 1) == 1
    assert add_executed_steps(2, 1) == 3
    assert add_executed_steps(3, None) == 3


def test_graph_state_and_branch_state_schemas_are_declared() -> None:
    assert "topic_input" in ResearchTopicState.__annotations__
    assert "outcome" in ResearchTopicState.__annotations__
    for field in ("url", "ordinal", "run_id", "thread_id", "query", "mode", "caller_id"):
        assert field in FetchBranchState.__annotations__
    for field in ("evidence_ids", "attempted_urls", "errors", "executed_steps"):
        assert field not in FetchBranchState.__annotations__


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
