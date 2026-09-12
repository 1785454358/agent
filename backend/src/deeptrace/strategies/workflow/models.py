"""Strict model-output contracts for the Workflow strategy."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from deeptrace.domain.evidence import Finding
from deeptrace.domain.research import TopicQuery


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

    @field_validator("queries")
    @classmethod
    def stable_dedupe_queries(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class WorkflowEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list, max_length=MAX_WORKFLOW_FINDINGS)
    unresolved_gaps: list[WorkflowGap] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_GAPS
    )
    sufficient: bool
