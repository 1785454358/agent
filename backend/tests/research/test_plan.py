"""Plans are typed DAGs with stable revisions and executable ready sets."""

import pytest
from pydantic import ValidationError

from deeptrace.research import (
    ContractBudget,
    ExecutionMode,
    PlanTask,
    ResearchContract,
    ResearchPlan,
    TaskBudget,
)
from deeptrace.domain import ResearchRequirement


def _contract(**changes) -> ResearchContract:
    values = {
        "run_id": "run-1",
        "goal": "Answer the research question",
        "requirements": (
            ResearchRequirement(id="r1", description="First requirement"),
            ResearchRequirement(id="r2", description="Second requirement"),
        ),
        "budget": ContractBudget(max_model_calls=20, finishing_calls=3),
    }
    values.update(changes)
    return ResearchContract.model_validate(values)


def _task(task_id: str = "t1", **changes) -> PlanTask:
    values = {
        "id": task_id,
        "type": "discover",
        "objective": f"Research task {task_id}",
        "in_scope": "Requirements assigned to this task",
        "out_of_scope": "Other tasks and final writing",
        "requirement_ids": ("r1",),
        "capabilities": ("search_web",),
        "query_seeds": (f"query {task_id}",),
        "expected_output": "Supported findings with source spans",
        "acceptance": ("At least one host-verified support",),
        "budget": TaskBudget(max_calls=3, max_pages=2),
    }
    values.update(changes)
    return PlanTask.model_validate(values)


def _plan(tasks: tuple[PlanTask, ...] | None = None, **changes) -> ResearchPlan:
    values = {
        "plan_id": "plan-1",
        "run_id": "run-1",
        "contract_revision": 1,
        "tasks": tasks if tasks is not None else (_task(),),
        "stop_conditions": ("All acceptance requirements are covered",),
    }
    values.update(changes)
    return ResearchPlan.model_validate(values)


def test_dag_has_stable_topological_order_and_parallel_ready_set() -> None:
    plan = _plan(
        (
            _task("t1"),
            _task("t2", requirement_ids=("r2",), query_seeds=("query t2",)),
            _task(
                "t3",
                type="synthesize",
                depends_on=("t1", "t2"),
                requirement_ids=("r1", "r2"),
                capabilities=(),
                query_seeds=(),
                budget=TaskBudget(max_calls=1, max_pages=0),
            ),
        )
    )
    assert plan.execution_order == ("t1", "t2", "t3")
    assert {task.id for task in plan.ready_tasks(())} == {"t1", "t2"}
    assert [task.id for task in plan.ready_tasks({"t1"})] == ["t2"]
    assert [task.id for task in plan.ready_tasks({"t1", "t2"})] == ["t3"]
    with pytest.raises(ValueError, match="unknown completed"):
        plan.ready_tasks({"t9"})


@pytest.mark.parametrize(
    "make_tasks,match",
    [
        (lambda: (_task("t1", depends_on=("t1",)),), "itself"),
        (lambda: (_task("t1", depends_on=("t3",)), _task("t2")), "missing dependencies"),
        (
            lambda: (
                _task("t1", depends_on=("t2",)),
                _task("t2", depends_on=("t1",)),
            ),
            "dependency cycle",
        ),
        (lambda: (_task("t1"), _task("t1")), "task ids must be unique"),
        (
            lambda: (
                _task(
                    "t1",
                    execution_hint=ExecutionMode.FANOUT,
                    depends_on=("t2",),
                ),
                _task("t2"),
            ),
            "fanout tasks",
        ),
    ],
)
def test_invalid_dags_are_rejected(make_tasks, match) -> None:
    with pytest.raises(ValidationError, match=match):
        _plan(make_tasks())


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": 2},
        {"revision": 2, "parent_revision": 2, "revision_reason": "reason"},
        {"revision": 1, "parent_revision": 1},
        {"stop_conditions": ()},
        {"tasks": ()},
    ],
)
def test_plan_revision_and_required_conditions_are_bounded(changes) -> None:
    with pytest.raises(ValidationError):
        _plan(**changes)


def test_next_revision_preserves_identity_and_adds_parent() -> None:
    plan = _plan()
    revised = plan.next_revision((_task("t1", objective="Refined task"),), reason="New evidence")
    assert revised.plan_id == plan.plan_id
    assert revised.contract_revision == plan.contract_revision
    assert revised.revision == 2
    assert revised.parent_revision == 1
    assert revised.tasks[0].objective == "Refined task"
    assert revised.execution_order == ("t1",)


def test_plan_and_review_survive_the_checkpoint_serializer() -> None:
    from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
    from deeptrace.research import review_plan

    plan = _plan(tasks=(_task("t1", requirement_ids=("r1", "r2")),))
    review = review_plan(plan, _contract(), allowed_capabilities={"search_web"})
    serializer = create_harness_checkpoint_serializer()
    restored_plan = serializer.loads_typed(serializer.dumps_typed(plan))
    restored_review = serializer.loads_typed(serializer.dumps_typed(review))
    assert restored_plan.execution_order == ("t1",)
    assert restored_review.accepted
    assert restored_review.covered_requirement_ids == ("r1", "r2")
