from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from deeptrace.domain import Evidence, EvidenceLifecycleStatus
from deeptrace.tools.scraper.urls import normalize_url_before_fetch


DEFAULT_MAX_BODY_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_CHUNK_BYTES = 16 * 1024


class EvidenceDraft(BaseModel):
    """Runtime ingestion input whose body never enters graph state."""

    model_config = ConfigDict(extra="forbid")

    canonical_url: str = Field(min_length=1, max_length=2_048)
    title: str = Field(min_length=1, max_length=500)
    media_type: str = Field(min_length=1, max_length=255)
    body: str
    fetched_at: datetime
    published_at: datetime | None = None
    source_quality: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceStore(Protocol):
    async def ingest(self, tenant_id: str, draft: EvidenceDraft) -> Evidence: ...

    async def get(self, tenant_id: str, evidence_id: str) -> Evidence: ...

    async def get_many(
        self, tenant_id: str, evidence_ids: Sequence[str]
    ) -> tuple[Evidence, ...]: ...

    async def read_body(self, tenant_id: str, evidence_id: str) -> str: ...

    async def read_chunks(
        self, tenant_id: str, evidence_id: str
    ) -> tuple[str, ...]: ...

    async def latest_for_source(
        self, tenant_id: str, canonical_url: str
    ) -> Evidence: ...


@dataclass(frozen=True)
class _StoredEvidence:
    evidence: Evidence
    chunks: tuple[str, ...]


class InMemoryEvidenceStore:
    """Concurrency-safe reference adapter with production store semantics."""

    def __init__(
        self,
        *,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        max_chunk_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
    ) -> None:
        if not isinstance(max_body_bytes, int) or isinstance(max_body_bytes, bool):
            raise TypeError("max_body_bytes must be an int")
        if not isinstance(max_chunk_bytes, int) or isinstance(max_chunk_bytes, bool):
            raise TypeError("max_chunk_bytes must be an int")
        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be greater than zero")
        if max_chunk_bytes < 4:
            raise ValueError("max_chunk_bytes must be at least four")
        if max_chunk_bytes > max_body_bytes:
            raise ValueError("max_chunk_bytes cannot exceed max_body_bytes")
        self._max_body_bytes = max_body_bytes
        self._max_chunk_bytes = max_chunk_bytes
        self._records: dict[tuple[str, str], _StoredEvidence] = {}
        self._latest_by_source: dict[tuple[str, str], str] = {}
        self._lock = asyncio.Lock()

    async def ingest(self, tenant_id: str, draft: EvidenceDraft) -> Evidence:
        tenant = _require_identifier("tenant_id", tenant_id)
        if not isinstance(draft, EvidenceDraft):
            raise TypeError("draft must be an EvidenceDraft")
        if not draft.body:
            raise ValueError("body must be non-empty")
        encoded_size = len(draft.body.encode("utf-8"))
        if encoded_size > self._max_body_bytes:
            raise ValueError(
                f"body exceeds {self._max_body_bytes} encoded bytes"
            )

        canonical_url = normalize_url_before_fetch(draft.canonical_url)
        content_hash = "sha256:" + hashlib.sha256(
            draft.body.encode("utf-8")
        ).hexdigest()
        evidence_id = _evidence_id(canonical_url, content_hash)
        chunks = _chunk_text(draft.body, self._max_chunk_bytes)

        async with self._lock:
            key = (tenant, evidence_id)
            existing = self._records.get(key)
            if existing is not None:
                return existing.evidence.model_copy(deep=True)

            source_key = (tenant, canonical_url)
            prior_id = self._latest_by_source.get(source_key)
            version = 1
            if prior_id is not None:
                prior_key = (tenant, prior_id)
                prior = self._records[prior_key]
                version = prior.evidence.version + 1
                self._records[prior_key] = _StoredEvidence(
                    evidence=prior.evidence.model_copy(
                        update={"status": EvidenceLifecycleStatus.SUPERSEDED},
                        deep=True,
                    ),
                    chunks=prior.chunks,
                )

            evidence = Evidence(
                id=evidence_id,
                canonical_url=canonical_url,
                title=draft.title,
                media_type=draft.media_type,
                content_hash=content_hash,
                fetched_at=draft.fetched_at,
                published_at=draft.published_at,
                source_quality=draft.source_quality,
                status=EvidenceLifecycleStatus.ACTIVE,
                version=version,
                supersedes=prior_id,
                metadata=draft.metadata,
            )
            self._records[key] = _StoredEvidence(evidence=evidence, chunks=chunks)
            self._latest_by_source[source_key] = evidence_id
            return evidence.model_copy(deep=True)

    async def get(self, tenant_id: str, evidence_id: str) -> Evidence:
        stored = await self._read_record(tenant_id, evidence_id)
        return stored.evidence.model_copy(deep=True)

    async def get_many(
        self, tenant_id: str, evidence_ids: Sequence[str]
    ) -> tuple[Evidence, ...]:
        tenant = _require_identifier("tenant_id", tenant_id)
        if isinstance(evidence_ids, (str, bytes)):
            raise TypeError("evidence_ids must be a sequence of identifiers")
        ids = tuple(
            _require_identifier("evidence_id", evidence_id)
            for evidence_id in evidence_ids
        )
        async with self._lock:
            return tuple(
                self._lookup(tenant, evidence_id).evidence.model_copy(deep=True)
                for evidence_id in ids
            )

    async def read_body(self, tenant_id: str, evidence_id: str) -> str:
        stored = await self._read_record(tenant_id, evidence_id)
        return "".join(stored.chunks)

    async def read_chunks(
        self, tenant_id: str, evidence_id: str
    ) -> tuple[str, ...]:
        stored = await self._read_record(tenant_id, evidence_id)
        return stored.chunks

    async def latest_for_source(
        self, tenant_id: str, canonical_url: str
    ) -> Evidence:
        tenant = _require_identifier("tenant_id", tenant_id)
        normalized = normalize_url_before_fetch(canonical_url)
        async with self._lock:
            try:
                evidence_id = self._latest_by_source[(tenant, normalized)]
            except KeyError as exc:
                raise KeyError("evidence source is not available for tenant") from exc
            return self._lookup(tenant, evidence_id).evidence.model_copy(deep=True)

    async def _read_record(
        self, tenant_id: str, evidence_id: str
    ) -> _StoredEvidence:
        tenant = _require_identifier("tenant_id", tenant_id)
        identifier = _require_identifier("evidence_id", evidence_id)
        async with self._lock:
            return self._lookup(tenant, identifier)

    def _lookup(self, tenant_id: str, evidence_id: str) -> _StoredEvidence:
        try:
            return self._records[(tenant_id, evidence_id)]
        except KeyError as exc:
            raise KeyError("evidence is not available for tenant") from exc


def _require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _evidence_id(canonical_url: str, content_hash: str) -> str:
    payload = f"{canonical_url}\0{content_hash}".encode("utf-8")
    return "evidence-" + hashlib.sha256(payload).hexdigest()


def _chunk_text(body: str, max_bytes: int) -> tuple[str, ...]:
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for character in body:
        character_size = len(character.encode("utf-8"))
        if current and current_size + character_size > max_bytes:
            chunks.append("".join(current))
            current = []
            current_size = 0
        current.append(character)
        current_size += character_size
    if current:
        chunks.append("".join(current))
    return tuple(chunks)
