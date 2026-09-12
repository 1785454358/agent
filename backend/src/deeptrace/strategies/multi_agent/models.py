"""Strict model-output contracts for the Multi-Agent strategy."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from deeptrace.domain.evidence import Finding
from deeptrace.strategies.workflow.models import MAX_WORKFLOW_GAPS, WorkflowGap


MAX_MA_RESEARCHERS = 5


class SupervisorEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["complete", "follow_up"]
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
