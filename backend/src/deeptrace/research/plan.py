"""A versioned, typed task DAG proposed by a planner and owned by the host."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Iterable
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from deeptrace.domain.execution import ExecutionIdentifier
from deeptrace.research.contract import ContractText

PlanIdentifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
TaskIdentifier = Annotated[str, StringConstraints(pattern=r"^t[1-9][0-9]?$")]
RequirementId = Annotated[str, StringConstraints(pattern=r"^r[1-6]$")]
CapabilityName = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")
]
QueryText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000)
]


class TaskType(StrEnum):
    DISCOVER = "discover"
    VERIFY = "verify"
    COMPARE = "compare"
    SYNTHESIZE = "synthesize"
    COMPUTE = "compute"


class ExecutionMode(StrEnum):
    AUTO = "auto"
    DIRECT = "direct"
    RETRIEVE = "retrieve"
    LOOP = "loop"
    FANOUT = "fanout"


class TaskBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_calls: int = Field(default=3, ge=1, le=20)
    max_pages: int = Field(default=2, ge=0, le=8)


class PlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: TaskIdentifier
    type: TaskType
    objective: ContractText
    in_scope: ContractText
    out_of_scope: ContractText
    requirement_ids: tuple[RequirementId, ...] = Field(min_length=1, max_length=6)
    depends_on: tuple[TaskIdentifier, ...] = Field(default_factory=tuple, max_length=12)
    capabilities: tuple[CapabilityName, ...] = Field(default_factory=tuple, max_length=8)
    query_seeds: tuple[QueryText, ...] = Field(default_factory=tuple, max_length=2)
    expected_output: ContractText
    acceptance: tuple[ContractText, ...] = Field(min_length=1, max_length=6)
    budget: TaskBudget = TaskBudget()
    execution_hint: ExecutionMode = ExecutionMode.AUTO

    @field_validator("requirement_ids", "depends_on", "capabilities", "query_seeds")
    @classmethod
    def unique_references(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must be unique")
        return value

    @model_validator(mode="after")
    def independent_task(self) -> PlanTask:
        if self.id in self.depends_on:
            raise ValueError("task cannot depend on itself")
        if self.execution_hint is ExecutionMode.FANOUT and self.depends_on:
            # Fan-out is intentionally limited to independent work; dependent
            # work belongs in a later ready-set wave.
            raise ValueError("fanout tasks must not declare dependencies")
        return self


class ResearchPlan(BaseModel):
    """Append-only plan revisions; tasks are the sole execution unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: PlanIdentifier
    run_id: ExecutionIdentifier
    contract_revision: int = Field(ge=1)
    revision: int = Field(default=1, ge=1)
    parent_revision: int | None = Field(default=None, ge=1)
    revision_reason: ContractText | None = None
    tasks: tuple[PlanTask, ...] = Field(min_length=1, max_length=12)
    stop_conditions: tuple[ContractText, ...] = Field(min_length=1, max_length=6)
    replan_triggers: tuple[ContractText, ...] = Field(default_factory=tuple, max_length=6)

    @field_validator("stop_conditions", "replan_triggers")
    @classmethod
    def unique_conditions(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must be unique")
        return value

    @model_validator(mode="after")
    def valid_dag_and_revision(self) -> ResearchPlan:
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task ids must be unique")
        known = set(task_ids)
        for task in self.tasks:
            missing = set(task.depends_on) - known
            if missing:
                raise ValueError(f"missing dependencies for {task.id}: {sorted(missing)}")
        if len(self.execution_order) != len(self.tasks):
            raise ValueError("research plan contains a dependency cycle")
        if self.revision == 1 and self.parent_revision is not None:
            raise ValueError("the initial plan cannot have a parent revision")
        if self.revision > 1 and (
            self.parent_revision is None
            or self.parent_revision >= self.revision
            or self.revision_reason is None
        ):
            raise ValueError("a plan revision requires its parent and reason")
        return self

    @property
    def content_digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def execution_order(self) -> tuple[str, ...]:
        """Stable topological order; ties keep the planner's task order."""
        remaining = {task.id: set(task.depends_on) for task in self.tasks}
        ordered: list[str] = []
        while remaining:
            ready = [
                task.id
                for task in self.tasks
                if task.id in remaining and not remaining[task.id]
            ]
            if not ready:
                return tuple(ordered)
            for task_id in ready:
                ordered.append(task_id)
                del remaining[task_id]
            for dependencies in remaining.values():
                dependencies.difference_update(ready)
        return tuple(ordered)

    def ready_tasks(self, completed: Collection[str]) -> tuple[PlanTask, ...]:
        known = {task.id for task in self.tasks}
        unknown = set(completed) - known
        if unknown:
            raise ValueError(f"unknown completed tasks: {sorted(unknown)}")
        done = set(completed)
        return tuple(
            task
            for task in self.tasks
            if task.id not in done and set(task.depends_on) <= done
        )

    def next_revision(
        self, tasks: Iterable[PlanTask], *, reason: ContractText
    ) -> ResearchPlan:
        return type(self).model_validate(
            {
                **self.model_dump(
                    exclude={"tasks", "revision", "parent_revision", "revision_reason"}
                ),
                "tasks": tuple(tasks),
                "revision": self.revision + 1,
                "parent_revision": self.revision,
                "revision_reason": reason,
            }
        )
