"""Cross-graph contracts for the reusable research topic subgraph."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from deeptrace.domain.evidence import EvidenceIdentifier
from deeptrace.domain.execution import ExecutionIdentifier, ResearchMode


MAX_TOPIC_QUERY_LENGTH = 1_000
MAX_TOPIC_URL_LENGTH = 2_048
MAX_TOPIC_ERROR_CODE_LENGTH = 128
MAX_TOPIC_ERRORS = 100
MAX_TOPIC_URLS = 100

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


class TopicStepError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["search", "fetch"]
    target: str = Field(default="", max_length=MAX_TOPIC_URL_LENGTH)
    code: TopicErrorCode


class ResearchTopicOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: TopicQuery
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

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "evidence_ids")

    @field_validator("attempted_urls")
    @classmethod
    def unique_attempted_urls(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "attempted_urls")
