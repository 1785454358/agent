import pytest
from pydantic import ValidationError

from deeptrace.domain.evidence import Finding
from deeptrace.domain.research import ResearchTopicOutcome, TopicStepError
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.plan_execute.models import ExecutorDecision, TaskPlan
from deeptrace.strategies.plan_execute.state import PlanExecuteState


def test_task_plan_is_strict_unique_and_bounded() -> None:
    plan = TaskPlan(queries=["a", "b", "a"])
    assert plan.queries == ["a", "b"]
    with pytest.raises(ValidationError):
        TaskPlan(queries=[])
    with pytest.raises(ValidationError):
        TaskPlan(queries=[str(index) for index in range(7)])
    with pytest.raises(ValidationError):
        TaskPlan(queries=["ok"], unexpected=1)


def test_executor_decision_is_strict_and_bounded() -> None:
    decision = ExecutorDecision(
        action="complete",
        reason="资料充足",
        findings=[],
        unresolved_gaps=[],
    )
    assert decision.action == "complete"
    with pytest.raises(ValidationError):
        ExecutorDecision(action="restart", reason="x")
    with pytest.raises(ValidationError):
        ExecutorDecision(action="replan", reason="")
    with pytest.raises(ValidationError):
        ExecutorDecision(action="replan", reason="x", unresolved_gaps=["g" * 600])
    with pytest.raises(ValidationError):
        ExecutorDecision(action="replan", reason="x", extra=1)


def test_plan_execute_state_declares_loop_channels() -> None:
    annotations = PlanExecuteState.__annotations__
    for field in (
        "plan_tasks",
        "completed_tasks",
        "current_task",
        "replan_count",
        "decision",
        "evidence_ids",
        "topic_outcomes",
        "executed_steps",
        "outcome",
    ):
        assert field in annotations, field


def test_plan_execute_models_round_trip_through_strict_serializer() -> None:
    state = {
        "decision": ExecutorDecision(
            action="replan",
            reason="缺少对比来源",
            findings=[
                Finding(
                    id="finding-1",
                    claim="claim",
                    evidence_ids=["evidence-1"],
                    confidence=0.9,
                )
            ],
            unresolved_gaps=["缺口"],
        ),
        "topic_outcome": ResearchTopicOutcome(
            query="q",
            evidence_ids=[],
            attempted_urls=["https://example.com/a"],
            errors=[
                TopicStepError(
                    stage="fetch", target="https://example.com/a", code="empty_page"
                )
            ],
            executed_steps=2,
        ),
    }
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(state))
    assert restored == state
    assert isinstance(restored["decision"], ExecutorDecision)
