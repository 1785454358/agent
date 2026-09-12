import pytest
from pydantic import ValidationError

from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.multi_agent.models import SupervisorEvaluation
from deeptrace.strategies.multi_agent.state import (
    MultiAgentState,
    ResearcherBranchState,
)


def test_supervisor_evaluation_is_strict_and_bounded() -> None:
    evaluation = SupervisorEvaluation(
        action="complete", reason="资料充足", findings=[], unresolved_gaps=[]
    )
    assert evaluation.action == "complete"
    with pytest.raises(ValidationError):
        SupervisorEvaluation(action="delegate", reason="x")
    with pytest.raises(ValidationError):
        SupervisorEvaluation(action="complete", reason="   ")
    with pytest.raises(ValidationError):
        SupervisorEvaluation(action="complete", reason="x", extra=1)


def test_multi_agent_state_declares_loop_channels() -> None:
    annotations = MultiAgentState.__annotations__
    for field in (
        "assignments",
        "round_number",
        "researcher_outcomes",
        "evidence_ids",
        "evaluation",
        "executed_steps",
        "outcome",
    ):
        assert field in annotations, field


def test_researcher_branch_state_is_private_per_researcher() -> None:
    annotations = ResearcherBranchState.__annotations__
    assert set(annotations) == {
        "run_id",
        "thread_id",
        "query",
        "researcher_index",
        "round_number",
    }


def test_supervisor_evaluation_round_trips_through_strict_serializer() -> None:
    value = {
        "evaluation": SupervisorEvaluation(
            action="follow_up",
            reason="缺少对比来源",
            findings=[],
            unresolved_gaps=["缺口"],
        )
    }
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(value))
    assert restored == value
    assert isinstance(restored["evaluation"], SupervisorEvaluation)
