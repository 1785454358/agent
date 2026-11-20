"""Scheduler exposes only dependency-ready tasks and blocks failed branches."""

import pytest

from deeptrace.research import (
    PlanScheduler,
    PlanTask,
    ResearchPlan,
    TaskBudget,
    TaskRunStatus,
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


def _dag() -> ResearchPlan:
    return _plan(
        _task("t1"),
        _task("t2"),
        _task("t3", depends_on=("t1", "t2")),
    )


def test_ready_set_respects_dependencies_and_concurrency_cap() -> None:
    scheduler = PlanScheduler(_dag(), max_parallel=1)
    assert [task.id for task in scheduler.next_batch()] == ["t1"]
    scheduler.mark_running("t1")
    scheduler.mark_completed("t1")
    assert [task.id for task in scheduler.next_batch()] == ["t2"]
    with pytest.raises(ValueError, match="not complete"):
        scheduler.mark_running("t3")
    scheduler.mark_running("t2")
    scheduler.mark_completed("t2")
    assert [task.id for task in scheduler.next_batch()] == ["t3"]
    scheduler.mark_running("t3")
    scheduler.mark_completed("t3")
    assert scheduler.complete and scheduler.finished


def test_failure_blocks_dependents_but_not_independent_work() -> None:
    scheduler = PlanScheduler(_dag())
    scheduler.mark_running("t1")
    scheduler.mark_failed("t1")
    assert scheduler.failed_task_ids == ("t1",)
    assert scheduler.blocked_task_ids == ("t3",)
    assert [task.id for task in scheduler.next_batch()] == ["t2"]
    assert scheduler.status_of("t3") is TaskRunStatus.BLOCKED
    scheduler.mark_running("t2")
    scheduler.mark_completed("t2")
    assert scheduler.finished
    assert not scheduler.complete


def test_initial_recovery_state_reclaims_completed_and_blocks_failed_branches() -> None:
    scheduler = PlanScheduler(_dag(), completed={"t1"}, failed={"t2"})
    assert scheduler.blocked_task_ids == ("t3",)
    assert scheduler.ready_tasks() == ()
    assert scheduler.finished

    resumed = PlanScheduler(_dag(), completed={"t1", "t2"})
    assert [task.id for task in resumed.next_batch()] == ["t3"]

    with pytest.raises(ValueError, match="failed task"):
        PlanScheduler(_dag(), completed={"t2", "t3"}, failed={"t1"})


def test_invalid_transitions_and_parallel_cap_are_rejected() -> None:
    scheduler = PlanScheduler(_dag(), max_parallel=2)
    assert [task.id for task in scheduler.next_batch()] == ["t1", "t2"]
    with pytest.raises(ValueError, match="not running"):
        scheduler.mark_completed("t1")
    scheduler.mark_running("t1")
    with pytest.raises(ValueError, match="not pending"):
        scheduler.mark_running("t1")
    with pytest.raises(ValueError, match="unknown"):
        scheduler.mark_running("t9")
    with pytest.raises(ValueError, match="max_parallel"):
        PlanScheduler(_dag(), max_parallel=0)
