"""Host observations of reads, not accepted factual or semantic supports."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.domain.evidence import ContentHash, EvidenceIdentifier

MAX_READ_ANCHORS = 64


class ReadEvidenceAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: EvidenceIdentifier
    version: int = Field(ge=1, strict=True)
    content_hash: ContentHash
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def ordered_range(self) -> "ReadEvidenceAnchor":
        if self.end <= self.start:
            raise ValueError("invalid_read_anchor_range")
        return self


def merge_read_anchors(left, right) -> list[ReadEvidenceAnchor]:
    merged = []
    seen = set()
    for candidate in [*(left or []), *(right or [])]:
        anchor = ReadEvidenceAnchor.model_validate(candidate)
        key = (
            anchor.evidence_id,
            anchor.version,
            anchor.content_hash,
            anchor.start,
            anchor.end,
        )
        if key not in seen:
            merged.append(anchor)
            seen.add(key)
        if len(merged) >= MAX_READ_ANCHORS:
            break
    return merged
