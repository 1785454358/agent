"""Controller turns an approved plan into one execution shape and task modes."""

import pytest

from deeptrace.domain import ResearchRequirement
from deeptrace.research import (
    ContractBudget,
    ControllerDecision,
    ExecutionMode,
    ExecutionShape,
    PlanRejectedError,
    PlanTask,
    ResearchContract,
    ResearchPlan,
    TaskBudget,
    decide_execution,
    review_plan,
)


def _contract() -> ResearchContract:
    return ResearchContract(
        run_id="run-1",
        goal="Answer the question",
        requirements=(ResearchRequirement(id="r1", description="One fact"),),
        budget=ContractBudget(max_model_calls=20, finishing_calls=3),
    )


def _task(task_id: str, **changes) -> PlanTask:
    values = {
        "id": task_id,
        "type": "discover",
        "objective": f"Task {task_id}",
        "in_scope": "Assigned requirement",
        "out_of_scope": "Final answer",
        "requirement_ids": ("r1",),
        "capabilities": ("search_web",),
        "query_seeds": (f"query {task_id}",),
        "expected_output": "Supported fact",
        "acceptance": ("One verified support",),
        "budget": TaskBudget(max_calls=2, max_pages=1),
    }
    values.update(changes)
    return PlanTask.model_validate(values)


def _plan(*tasks: PlanTask) -> ResearchPlan:
    return ResearchPlan(
        plan_id="plan-1",
        run_id="run-1",
        contract_revision=1,
        tasks=tasks,
        stop_conditions=("All requirements covered",),
    )


def _decision(plan: ResearchPlan, **kwargs) -> ControllerDecision:
    review = review_plan(
        plan, _contract(), allowed_capabilities={"search_web", "read_evidence"}
    )
    return decide_execution(plan, review, **kwargs)


@pytest.mark.parametrize("change", [
    {"plan_id": "another-plan"},
    {"tasks": (_task("t1", query_seeds=("changed query",)),)},
    {"contract_revision": 2},
])
def test_review_cannot_authorize_another_plan_with_the_same_revision(change):
    plan = _plan(_task("t1"))
    review = review_plan(plan, _contract())
    changed = ResearchPlan.model_validate({**plan.model_dump(), **change})
    with pytest.raises(ValueError, match="review"):
        decide_execution(changed, review)


def test_shape_and_default_modes_follow_task_type_and_dependencies() -> None:
    decision = _decision(_plan(_task("t1")))
    assert decision.shape is ExecutionShape.RETRIEVE
    assert decision.max_parallel == 1
    assert decision.task_modes == {"t1": ExecutionMode.RETRIEVE}

    decision = _decision(_plan(_task("t1"), _task("t2")))
    assert decision.shape is ExecutionShape.FANOUT
    assert decision.max_parallel == 2

    decision = _decision(
        _plan(_task("t1"), _task("t2", depends_on=("t1",))),
        max_parallel=8,
    )
    assert decision.shape is ExecutionShape.DAG
    assert decision.max_parallel == 2

    decision = _decision(_plan(_task(
        "t1",
        type="synthesize",
        capabilities=(),
        query_seeds=(),
        budget=TaskBudget(max_calls=1, max_pages=0),
    )))
    assert decision.shape is ExecutionShape.DIRECT
    assert decision.task_modes["t1"] is ExecutionMode.DIRECT


def test_explicit_execution_hint_wins_over_task_type_default() -> None:
    decision = _decision(_plan(_task("t1", type="verify", execution_hint="loop")))
    assert decision.shape is ExecutionShape.LOOP
    assert decision.task_modes["t1"] is ExecutionMode.LOOP


def test_rejected_or_stale_plan_review_cannot_execute() -> None:
    plan = _plan(_task("t1"))
    rejected = review_plan(
        plan,
        ResearchContract(run_id="run-1", goal="Empty contract"),
        allowed_capabilities={"search_web"},
    )
    with pytest.raises(PlanRejectedError):
        decide_execution(plan, rejected)

    accepted = review_plan(
        plan, _contract(), allowed_capabilities={"search_web"}
    )
    stale = accepted.model_copy(update={"plan_revision": 2})
    with pytest.raises(ValueError, match="revision"):
        decide_execution(plan, stale)


def test_controller_decision_survives_the_checkpoint_serializer() -> None:
    from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer

    decision = _decision(
        _plan(_task("t1"), _task("t2", depends_on=("t1",)))
    )
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(decision))
    assert restored == decision
