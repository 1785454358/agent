"""Strict model-output contracts for the Plan-and-Execute strategy."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from deeptrace.domain import CoverageAssessment, ResearchRequirement
from deeptrace.domain.research import TopicQuery
from deeptrace.strategies.evidence_evaluation import FindingDraft
from deeptrace.strategies.evidence_references import (
    ReferenceFindingDraft,
    ReferenceSourceCheck,
)
from deeptrace.strategies.workflow.models import MAX_WORKFLOW_GAPS, WorkflowGap

MAX_PLAN_TASKS = 6


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[TopicQuery] = Field(min_length=1, max_length=MAX_PLAN_TASKS)
    requirements: list[ResearchRequirement] = Field(min_length=1, max_length=6)

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
    findings: list[FindingDraft] = Field(
        default_factory=list,
        max_length=MAX_WORKFLOW_GAPS,
    )
    coverage: CoverageAssessment
    unresolved_gaps: list[WorkflowGap] = Field(
        default_factory=list,
        max_length=MAX_WORKFLOW_GAPS,
    )


class ReferenceExecutorDecision(ExecutorDecision):
    """Live v3 output; ExecutorDecision remains the historical v2 DTO."""

    findings: list[ReferenceFindingDraft] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_GAPS
    )
    source_checks: list[ReferenceSourceCheck] = Field(
        default_factory=list, max_length=8
    )
