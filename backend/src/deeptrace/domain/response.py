from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from deeptrace.domain.evidence import EvidenceIdentifier
from deeptrace.domain.execution import ResearchOutcome, ResponseMode


MAX_RESPONSE_QUESTION_LENGTH = 20_000
MAX_RESPONSE_CONTENT_LENGTH = 50_000
MAX_CITATION_MARKER_LENGTH = 32
MAX_CITATIONS = 100
MAX_ACTIVE_EVIDENCE_IDS = 100
MAX_PARTIAL_REASON_LENGTH = 500

Question = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_RESPONSE_QUESTION_LENGTH,
    ),
]
ResponseContent = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_RESPONSE_CONTENT_LENGTH,
    ),
]
CitationMarker = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_CITATION_MARKER_LENGTH,
    ),
]
PartialReason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_PARTIAL_REASON_LENGTH,
    ),
]


def _require_unique(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")
    return values


class CitationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: EvidenceIdentifier
    marker: CitationMarker


class ResponseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Question
    response_mode: ResponseMode
    research_outcome: ResearchOutcome | None = None
    active_evidence_ids: list[EvidenceIdentifier] = Field(
        default_factory=list,
        max_length=MAX_ACTIVE_EVIDENCE_IDS,
    )
    context_notes: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("active_evidence_ids")
    @classmethod
    def unique_active_evidence_ids(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "active_evidence_ids")


class ResponseOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_mode: ResponseMode
    content: ResponseContent
    citations: list[CitationRef] = Field(
        default_factory=list,
        max_length=MAX_CITATIONS,
    )
    cited_evidence_ids: list[EvidenceIdentifier] = Field(
        default_factory=list,
        max_length=MAX_CITATIONS,
    )
    partial_reason: PartialReason | None = None

    @field_validator("cited_evidence_ids")
    @classmethod
    def unique_cited_evidence_ids(cls, value: list[str]) -> list[str]:
        return _require_unique(value, "cited_evidence_ids")

    @field_validator("citations")
    @classmethod
    def unique_citation_evidence_ids(
        cls, value: list[CitationRef]
    ) -> list[CitationRef]:
        evidence_ids = [citation.evidence_id for citation in value]
        _require_unique(evidence_ids, "citation evidence_ids")
        return value

    @model_validator(mode="after")
    def validate_reference_contract(self) -> ResponseOutcome:
        citation_ids = [citation.evidence_id for citation in self.citations]
        if citation_ids != self.cited_evidence_ids:
            raise ValueError("cited_evidence_ids must match citation evidence_ids")
        if self.partial_reason is None and not citation_ids:
            raise ValueError("complete responses require evidence references")
        return self
