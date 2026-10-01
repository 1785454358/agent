"""Long-term memory contracts spanning threads and sessions."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deeptrace.domain.evidence import EvidenceIdentifier

MAX_MEMORY_CONTENT_LENGTH = 2_000
MAX_MEMORY_SUBJECT_LENGTH = 200
MAX_MEMORY_SOURCES = 20
STALE_AFTER_DAYS = 30

MemoryScope = Literal["user", "workspace", "thread", "global"]
MemoryNamespace = tuple[str, str, str]


class RecalledMemory(TypedDict):
    id: str
    version: int
    type: str
    subject: str
    content: str
    source_evidence_ids: list[str]
    confidence: float
    updated_at: str
    expires_at: str | None


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
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
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
    def derive_stable_id(self) -> MemoryRecord:
        if not self.id:
            digest = hashlib.sha256(
                f"{self.identity()}|v{self.version}".encode()
            ).hexdigest()[:32]
            self.id = f"mem-{digest}"
        return self

    def identity(self) -> str:
        return f"{self.namespace}|{self.type.value}|{self.subject}"

    def store_key(self) -> str:
        return f"{self.identity()}|v{self.version}"


def next_memory_version(
    record: MemoryRecord,
    previous: MemoryRecord | None,
    *,
    allow_reactivate: bool = True,
) -> MemoryRecord:
    """Pure version decision; stores commit it and superseding atomically."""
    if previous is None:
        return record.model_copy(deep=True)
    if previous.status is MemoryStatus.DELETED and not allow_reactivate:
        return previous.model_copy(deep=True)
    live = previous.status is MemoryStatus.ACTIVE and (
        previous.expires_at is None or previous.expires_at > record.updated_at
    )
    if (
        live
        and previous.content == record.content
        and previous.source_evidence_ids == record.source_evidence_ids
    ):
        return previous.model_copy(deep=True)
    return MemoryRecord.model_validate(
        {
            **record.model_dump(),
            "id": "",
            "version": previous.version + 1,
            "supersedes": previous.id,
        }
    )


def current_memories(records: list[MemoryRecord]) -> list[MemoryRecord]:
    """Newest version is authoritative, even when it is deleted or expired."""
    latest: dict[str, MemoryRecord] = {}
    for record in records:
        previous = latest.get(record.identity())
        if previous is None or record.version > previous.version:
            latest[record.identity()] = record
    return sorted(latest.values(), key=lambda r: r.identity())
