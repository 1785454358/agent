"""Strict model-output contracts for the Workflow strategy."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from deeptrace.domain import CoverageAssessment, ResearchRequirement
from deeptrace.domain.research import TopicQuery
from deeptrace.strategies.evidence_evaluation import FindingDraft
from deeptrace.strategies.evidence_references import (
    ReferenceFindingDraft,
    ReferenceSourceCheck,
)

MAX_WORKFLOW_QUERIES = 10
MAX_WORKFLOW_FINDINGS = 50
MAX_WORKFLOW_GAPS = 50
MAX_WORKFLOW_GAP_LENGTH = 500

WorkflowGap = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_WORKFLOW_GAP_LENGTH,
    ),
]


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[TopicQuery] = Field(min_length=1, max_length=MAX_WORKFLOW_QUERIES)
    requirements: list[ResearchRequirement] = Field(min_length=1, max_length=6)

    @field_validator("queries")
    @classmethod
    def stable_dedupe_queries(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class WorkflowEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[FindingDraft] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_FINDINGS
    )
    coverage: CoverageAssessment
    unresolved_gaps: list[WorkflowGap] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_GAPS
    )
    sufficient: bool


class ReferenceWorkflowEvaluation(WorkflowEvaluation):
    """Live v3 output; WorkflowEvaluation remains the historical v2 DTO."""

    findings: list[ReferenceFindingDraft] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_FINDINGS
    )
    source_checks: list[ReferenceSourceCheck] = Field(
        default_factory=list, max_length=8
    )
