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
)

from deeptrace.domain.evidence import EvidenceIdentifier
from deeptrace.domain.execution import ExecutionIdentifier, ResearchMode
from deeptrace.domain.agent import AgentOutcome


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


class TopicStepError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["search", "fetch"]
    target: str = Field(default="", max_length=MAX_TOPIC_URL_LENGTH)
    code: TopicErrorCode


class ResearchTopicOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: TopicQuery
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
    outcomes: "list[ResearchTopicOutcome]",
) -> list[str]:
    """Open todo contents across one or more topic outcomes."""
    items: list[str] = []
    for outcome in outcomes:
        items.extend(outcome.unfinished_todos)
    return items
