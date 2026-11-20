"""Deterministic ready-set scheduling for a ResearchPlan DAG."""

from __future__ import annotations

from collections.abc import Collection
from enum import StrEnum

from deeptrace.research.plan import PlanTask, ResearchPlan, TaskIdentifier


class TaskRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


_TERMINAL = {
    TaskRunStatus.COMPLETED,
    TaskRunStatus.FAILED,
    TaskRunStatus.BLOCKED,
}


class PlanScheduler:
    """Tracks task lifecycle; callers dispatch only the returned ready set."""

    def __init__(
        self,
        plan: ResearchPlan,
        *,
        max_parallel: int = 4,
        completed: Collection[str] = (),
        failed: Collection[str] = (),
    ) -> None:
        if not 1 <= max_parallel <= 16:
            raise ValueError("max_parallel must be between 1 and 16")
        self._plan = plan
        self._max_parallel = max_parallel
        self._tasks = {task.id: task for task in plan.tasks}
        self._status = {task.id: TaskRunStatus.PENDING for task in plan.tasks}
        self._set_initial(completed, TaskRunStatus.COMPLETED)
        self._set_initial(failed, TaskRunStatus.FAILED)
        self._block_dependents()
        for task in self._plan.tasks:
            if self._status[task.id] is not TaskRunStatus.COMPLETED:
                continue
            if any(
                self._status[dependency]
                in {TaskRunStatus.FAILED, TaskRunStatus.BLOCKED}
                for dependency in task.depends_on
            ):
                raise ValueError(
                    f"completed task depends on a failed task: {task.id}"
                )

    @property
    def plan(self) -> ResearchPlan:
        return self._plan

    @property
    def max_parallel(self) -> int:
        return self._max_parallel

    @property
    def complete(self) -> bool:
        return all(
            status is TaskRunStatus.COMPLETED
            for status in self._status.values()
        )

    @property
    def finished(self) -> bool:
        return all(status in _TERMINAL for status in self._status.values())

    @property
    def failed_task_ids(self) -> tuple[str, ...]:
        return tuple(
            task.id
            for task in self._plan.tasks
            if self._status[task.id] is TaskRunStatus.FAILED
        )

    @property
    def blocked_task_ids(self) -> tuple[str, ...]:
        return tuple(
            task.id
            for task in self._plan.tasks
            if self._status[task.id] is TaskRunStatus.BLOCKED
        )

    def status_of(self, task_id: str) -> TaskRunStatus:
        self._require_known(task_id)
        return self._status[task_id]

    def ready_tasks(self) -> tuple[PlanTask, ...]:
        return tuple(
            task
            for task in self._plan.tasks
            if self._status[task.id] is TaskRunStatus.PENDING
            and all(
                self._status[dependency] is TaskRunStatus.COMPLETED
                for dependency in task.depends_on
            )
        )

    def next_batch(self) -> tuple[PlanTask, ...]:
        return self.ready_tasks()[: self._max_parallel]

    def mark_running(self, task_id: str) -> None:
        task = self._require_known(task_id)
        if self._status[task_id] is not TaskRunStatus.PENDING:
            raise ValueError(f"task is not pending: {task_id}")
        if not all(
            self._status[dependency] is TaskRunStatus.COMPLETED
            for dependency in task.depends_on
        ):
            raise ValueError(f"task dependencies are not complete: {task_id}")
        self._status[task_id] = TaskRunStatus.RUNNING

    def mark_completed(self, task_id: str) -> None:
        self._require_known(task_id)
        if self._status[task_id] is not TaskRunStatus.RUNNING:
            raise ValueError(f"task is not running: {task_id}")
        self._status[task_id] = TaskRunStatus.COMPLETED

    def mark_failed(self, task_id: str) -> None:
        self._require_known(task_id)
        if self._status[task_id] is not TaskRunStatus.RUNNING:
            raise ValueError(f"task is not running: {task_id}")
        self._status[task_id] = TaskRunStatus.FAILED
        self._block_dependents()

    def _set_initial(
        self, task_ids: Collection[str], status: TaskRunStatus
    ) -> None:
        unknown = set(task_ids) - set(self._tasks)
        if unknown:
            raise ValueError(f"unknown tasks: {sorted(unknown)}")
        for task_id in task_ids:
            if self._status[task_id] is not TaskRunStatus.PENDING:
                raise ValueError(f"task reached two initial states: {task_id}")
            self._status[task_id] = status

    def _block_dependents(self) -> None:
        changed = True
        while changed:
            changed = False
            for task in self._plan.tasks:
                if self._status[task.id] is not TaskRunStatus.PENDING:
                    continue
                if any(
                    self._status[dependency]
                    in {TaskRunStatus.FAILED, TaskRunStatus.BLOCKED}
                    for dependency in task.depends_on
                ):
                    self._status[task.id] = TaskRunStatus.BLOCKED
                    changed = True

    def _require_known(self, task_id: TaskIdentifier) -> PlanTask:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise ValueError(f"unknown task: {task_id}") from exc
