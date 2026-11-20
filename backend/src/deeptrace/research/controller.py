"""Choose execution shape and per-task executors from an approved plan."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.research.critic import PlanReview
from deeptrace.research.plan import (
    ExecutionMode,
    PlanTask,
    ResearchPlan,
    TaskIdentifier,
    TaskType,
)


class ExecutionShape(StrEnum):
    DIRECT = "direct"
    RETRIEVE = "retrieve"
    LOOP = "loop"
    FANOUT = "fanout"
    DAG = "dag"


class PlanRejectedError(ValueError):
    """A plan that failed host review must never reach execution."""


class ControllerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(min_length=1, max_length=128)
    plan_revision: int = Field(ge=1)
    shape: ExecutionShape
    max_parallel: int = Field(ge=1, le=16)
    task_modes: dict[TaskIdentifier, ExecutionMode] = Field(max_length=12)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def concrete_modes(self) -> ControllerDecision:
        if any(mode is ExecutionMode.AUTO for mode in self.task_modes.values()):
            raise ValueError("controller must resolve every execution hint")
        return self


def _default_mode(task: PlanTask) -> ExecutionMode:
    if task.execution_hint is not ExecutionMode.AUTO:
        return task.execution_hint
    if task.type is TaskType.SYNTHESIZE:
        return ExecutionMode.DIRECT
    if task.type is TaskType.DISCOVER:
        return ExecutionMode.RETRIEVE
    return ExecutionMode.LOOP


def _shape_for(plan: ResearchPlan, modes: dict[str, ExecutionMode]) -> ExecutionShape:
    if any(task.depends_on for task in plan.tasks):
        return ExecutionShape.DAG
    if len(plan.tasks) > 1:
        return ExecutionShape.FANOUT
    mode = modes[plan.tasks[0].id]
    if mode is ExecutionMode.DIRECT:
        return ExecutionShape.DIRECT
    if mode is ExecutionMode.LOOP:
        return ExecutionShape.LOOP
    return ExecutionShape.RETRIEVE


def decide_execution(
    plan: ResearchPlan,
    review: PlanReview,
    *,
    max_parallel: int = 4,
) -> ControllerDecision:
    """Resolve a plan into one shape and one concrete executor per task."""
    if not 1 <= max_parallel <= 16:
        raise ValueError("max_parallel must be between 1 and 16")
    if not review.accepted:
        raise PlanRejectedError("research plan was rejected by the host critic")
    if review.plan_revision != plan.revision:
        raise ValueError("plan review does not belong to this plan revision")
    if (review.plan_id != plan.plan_id
            or review.contract_revision != plan.contract_revision
            or review.plan_digest != plan.content_digest):
        raise ValueError("plan review does not belong to this plan content")

    modes = {task.id: _default_mode(task) for task in plan.tasks}
    shape = _shape_for(plan, modes)
    parallel = (
        min(max_parallel, len(plan.tasks))
        if shape in {ExecutionShape.FANOUT, ExecutionShape.DAG}
        else 1
    )
    return ControllerDecision(
        plan_id=plan.plan_id,
        plan_revision=plan.revision,
        shape=shape,
        max_parallel=parallel,
        task_modes=modes,
        reason=f"selected {shape.value} for {len(plan.tasks)} planned tasks",
    )
