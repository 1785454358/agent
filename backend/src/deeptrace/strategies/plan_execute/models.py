"""Strict model-output contracts for the Plan-and-Execute strategy."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from deeptrace.domain.evidence import Finding
from deeptrace.domain.research import TopicQuery
from deeptrace.strategies.workflow.models import MAX_WORKFLOW_GAPS, WorkflowGap


MAX_PLAN_TASKS = 6


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[TopicQuery] = Field(min_length=1, max_length=MAX_PLAN_TASKS)

    @field_validator("queries")
    @classmethod
    def stable_dedupe_queries(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class ExecutorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["complete", "replan", "block"]
    reason: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ]
    findings: list[Finding] = Field(
        default_factory=list,
        max_length=MAX_WORKFLOW_GAPS,
    )
    unresolved_gaps: list[WorkflowGap] = Field(
        default_factory=list,
        max_length=MAX_WORKFLOW_GAPS,
    )
