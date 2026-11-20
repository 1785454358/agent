"""Host observations of reads, not accepted factual or semantic supports."""

from typing import Annotated

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from deeptrace.domain.evidence import ContentHash, EvidenceIdentifier

MAX_READ_ANCHORS = 64


class ReadEvidenceAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: EvidenceIdentifier
    version: int = Field(ge=1, strict=True)
    content_hash: ContentHash
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    # Host request metadata for selecting already-read text, never a support.
    queries: tuple[Annotated[str, Field(min_length=1, max_length=1000)], ...] = Field(
        default=(), max_length=6, validation_alias=AliasChoices("queries", "query"),
    )

    @field_validator("queries", mode="before")
    @classmethod
    def legacy_query(cls, value):
        return () if value is None else (value,) if isinstance(value, str) else value

    @property
    def query(self) -> str | None:
        return self.queries[0] if self.queries else None

    @property
    def range_key(self) -> tuple:
        return self.evidence_id, self.version, self.content_hash, self.start, self.end

    @model_validator(mode="after")
    def ordered_range(self) -> "ReadEvidenceAnchor":
        if self.end <= self.start:
            raise ValueError("invalid_read_anchor_range")
        return self


def merge_read_anchors(left, right) -> list[ReadEvidenceAnchor]:
    merged = []
    positions = {}
    for candidate in [*(left or []), *(right or [])]:
        anchor = ReadEvidenceAnchor.model_validate(candidate)
        key = anchor.range_key
        if key in positions:
            index = positions[key]
            queries = tuple(dict.fromkeys((*merged[index].queries, *anchor.queries)))[:6]
            merged[index] = merged[index].model_copy(update={"queries": queries})
        elif len(merged) < MAX_READ_ANCHORS:
            positions[key] = len(merged)
            merged.append(anchor)
    return merged
