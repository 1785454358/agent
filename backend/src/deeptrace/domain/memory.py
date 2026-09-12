"""Long-term memory contracts spanning threads and sessions."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deeptrace.domain.evidence import EvidenceIdentifier


MAX_MEMORY_CONTENT_LENGTH = 2_000
MAX_MEMORY_SUBJECT_LENGTH = 200
MAX_MEMORY_SOURCES = 20
STALE_AFTER_DAYS = 30

MemoryScope = Literal["user", "workspace", "thread", "global"]
MemoryNamespace = tuple[str, str, str]


class MemoryType(StrEnum):
    PREFERENCE = "preference"
    FACT = "fact"
    EVIDENCE = "evidence"
    EPISODE = "episode"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    DELETED = "deleted"


class MemoryRecord(BaseModel):
    """One versioned long-term memory; identity is (type, namespace, subject)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="", max_length=128)
    type: MemoryType
    namespace: MemoryNamespace
    subject: str = Field(
        min_length=1,
        max_length=MAX_MEMORY_SUBJECT_LENGTH,
    )
    content: str = Field(
        min_length=1,
        max_length=MAX_MEMORY_CONTENT_LENGTH,
    )
    source_evidence_ids: list[EvidenceIdentifier] = Field(
        default_factory=list,
        max_length=MAX_MEMORY_SOURCES,
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    status: MemoryStatus = MemoryStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    supersedes: str | None = None

    @field_validator("source_evidence_ids")
    @classmethod
    def unique_source_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source_evidence_ids must be unique")
        return value

    @model_validator(mode="after")
    def derive_stable_id(self) -> "MemoryRecord":
        if not self.id:
            digest = hashlib.sha256(
                f"{self.identity()}|v{self.version}".encode("utf-8")
            ).hexdigest()[:32]
            self.id = f"mem-{digest}"
        return self

    def identity(self) -> str:
        return f"{self.namespace}|{self.type.value}|{self.subject}"

    def store_key(self) -> str:
        return f"{self.identity()}|v{self.version}"
