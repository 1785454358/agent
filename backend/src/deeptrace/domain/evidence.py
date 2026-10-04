from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

MAX_EVIDENCE_ID_LENGTH = 128
MAX_EVIDENCE_URL_LENGTH = 2_048
MAX_EVIDENCE_TITLE_LENGTH = 500
MAX_EVIDENCE_MEDIA_TYPE_LENGTH = 255
MAX_EVIDENCE_CONTENT_HASH_LENGTH = 128
MAX_EVIDENCE_METADATA_BYTES = 16 * 1024
MAX_EVIDENCE_METADATA_ENTRIES = 100

EvidenceIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_EVIDENCE_ID_LENGTH,
    ),
]
CanonicalUrl = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_EVIDENCE_URL_LENGTH,
    ),
]
EvidenceTitle = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_EVIDENCE_TITLE_LENGTH,
    ),
]
MediaType = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_EVIDENCE_MEDIA_TYPE_LENGTH,
    ),
]
ContentHash = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_EVIDENCE_CONTENT_HASH_LENGTH,
    ),
]


class EvidenceLifecycleStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    DELETED = "deleted"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: EvidenceIdentifier
    canonical_url: CanonicalUrl
    title: EvidenceTitle
    media_type: MediaType
    content_hash: ContentHash
    fetched_at: datetime
    published_at: datetime | None = None
    source_quality: float = Field(ge=0.0, le=1.0)
    status: EvidenceLifecycleStatus
    version: int = Field(ge=1)
    supersedes: EvidenceIdentifier | None = None
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        max_length=MAX_EVIDENCE_METADATA_ENTRIES,
    )

    @field_validator("fetched_at", "published_at")
    @classmethod
    def timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("evidence timestamps must be timezone-aware")
        return value

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(
        cls,
        value: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        try:
            serialized = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must be JSON-compatible") from exc
        if len(serialized.encode("utf-8")) > MAX_EVIDENCE_METADATA_BYTES:
            raise ValueError(
                f"metadata exceed {MAX_EVIDENCE_METADATA_BYTES} encoded bytes"
            )
        return value

    @model_validator(mode="after")
    def does_not_supersede_itself(self) -> Evidence:
        if self.supersedes == self.id:
            raise ValueError("evidence cannot supersede itself")
        return self


class EvidenceSupport(BaseModel):
    """A host-resolved verbatim quote, not a semantic entailment guarantee."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: EvidenceIdentifier
    version: int = Field(ge=1)
    content_hash: ContentHash
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    quote: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_range(self) -> EvidenceSupport:
        if self.end <= self.start or self.end - self.start != len(self.quote):
            raise ValueError("support_range_mismatch")
        return self


class Finding(BaseModel):
    id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    supports: list[EvidenceSupport] = Field(default_factory=list, max_length=3)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value

    @model_validator(mode="after")
    def support_sources_are_listed(self) -> Finding:
        if any(s.evidence_id not in self.evidence_ids for s in self.supports):
            raise ValueError("support_evidence_not_listed")
        return self
