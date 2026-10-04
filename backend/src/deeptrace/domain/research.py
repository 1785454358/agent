"""Cross-graph contracts for the reusable research topic subgraph."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from deeptrace.domain.agent import AgentOutcome
from deeptrace.domain.coverage import (
    CoverageAssessment,
    RequirementCoverage,
    ResearchRequirement,
)
from deeptrace.domain.evidence import EvidenceIdentifier, Finding
from deeptrace.domain.evidence_anchor import MAX_READ_ANCHORS, ReadEvidenceAnchor
from deeptrace.domain.execution import ExecutionIdentifier, ResearchMode

__all__ = [
    "INCOMPLETE_PLAN_REASON",
    "CoverageAssessment",
    "RequirementCoverage",
    "ResearchRequirement",
    "ResearchTopicInput",
    "ResearchTopicOutcome",
    "TopicStepError",
    "unfinished_plan_items",
]

MAX_TOPIC_QUERY_LENGTH = 1_000
MAX_TOPIC_URL_LENGTH = 2_048
MAX_TOPIC_ERROR_CODE_LENGTH = 128
MAX_TOPIC_ERRORS = 100
MAX_TOPIC_URLS = 100
MAX_TOPIC_TODOS = 100

# Termination reason used when the executor's plan still had open items.
INCOMPLETE_PLAN_REASON = "incomplete_plan"

TopicQuery = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_TOPIC_QUERY_LENGTH,
    ),
]
TopicUrl = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_TOPIC_URL_LENGTH,
    ),
]
TopicErrorCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_TOPIC_ERROR_CODE_LENGTH,
    ),
]


def _require_unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")
    return values


class ResearchTopicInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: ExecutionIdentifier
    thread_id: ExecutionIdentifier
    query: TopicQuery
    max_pages: int = Field(default=3, ge=1, le=8)
    mode: ResearchMode
    caller_id: ExecutionIdentifier
    original_task: str = ""
    constraints: list[str] = Field(default_factory=list)
    context_notes: list[str] = Field(default_factory=list)
    evidence_contract_version: int = Field(default=1, ge=1, le=3)
    requirements: list[ResearchRequirement] = Field(default_factory=list, max_length=6)
    target_requirement_ids: list[
        Annotated[str, StringConstraints(pattern=r"^r[1-6]$")]
    ] = Field(default_factory=list, max_length=6)
    research_gaps: list[
        Annotated[str, StringConstraints(min_length=1, max_length=500)]
    ] = Field(default_factory=list, max_length=6)
    # Host-populated internal branch field, never part of a model tool schema.
    authorized_evidence_ids: list[EvidenceIdentifier] = Field(
        default_factory=list, max_length=100
    )

    @field_validator("target_requirement_ids", "authorized_evidence_ids")
    @classmethod
    def unique_context_ids(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _require_unique(values, info.field_name)

    @model_validator(mode="after")
    def consistent_requirements(self) -> ResearchTopicInput:
        ids = [requirement.id for requirement in self.requirements]
        _require_unique(ids, "requirements")
        if not set(self.target_requirement_ids) <= set(ids):
            raise ValueError("target_requirement_ids must reference requirements")
        return self


class TopicStepError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["search", "fetch", "read"]
    target: str = Field(default="", max_length=MAX_TOPIC_URL_LENGTH)
    code: TopicErrorCode


class ResearchTopicOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: TopicQuery
    read_anchors: list[ReadEvidenceAnchor] = Field(
        default_factory=list, max_length=MAX_READ_ANCHORS
    )
    read_anchor_diagnostics: list[str] = Field(default_factory=list, max_length=100)
    research_findings: list[Finding] = Field(default_factory=list, max_length=20)
    research_finding_diagnostics: list[str] = Field(
        default_factory=list, max_length=100
    )
    agent_outcome: AgentOutcome | None = None
    evidence_ids: list[EvidenceIdentifier] = Field(
        default_factory=list,
        max_length=MAX_TOPIC_URLS,
    )
    attempted_urls: list[TopicUrl] = Field(
        default_factory=list,
        max_length=MAX_TOPIC_URLS,
    )
    errors: list[TopicStepError] = Field(
        default_factory=list,
        max_length=MAX_TOPIC_ERRORS,
    )
    executed_steps: int = Field(default=0, ge=0)
    # Plan completeness reported by the agent loop. Defaults keep outcomes
    # produced before the plan existed (and old checkpoints) loadable.
    plan_total: int = Field(default=0, ge=0)
    plan_completed: int = Field(default=0, ge=0)
    unfinished_todos: list[str] = Field(
        default_factory=list,
        max_length=MAX_TOPIC_TODOS,
    )

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "evidence_ids")

    @field_validator("attempted_urls")
    @classmethod
    def unique_attempted_urls(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "attempted_urls")

    @field_validator("plan_completed")
    @classmethod
    def completed_within_total(cls, value: int, info: ValidationInfo) -> int:
        total = info.data.get("plan_total")
        if total is not None and value > total:
            raise ValueError("plan_completed cannot exceed plan_total")
        return value

    @property
    def plan_complete(self) -> bool:
        """True when there was no plan or every planned item finished."""
        return self.plan_completed >= self.plan_total


def unfinished_plan_items(
    outcomes: list[ResearchTopicOutcome],
) -> list[str]:
    """Open todo contents across one or more topic outcomes."""
    items: list[str] = []
    for outcome in outcomes:
        items.extend(outcome.unfinished_todos)
    return items
