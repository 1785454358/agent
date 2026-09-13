"""SQL-backed Evidence Store: page bodies survive restarts and processes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deeptrace.domain import Evidence, EvidenceLifecycleStatus
from deeptrace.persistence.orm import EvidenceRecordRow
from deeptrace.tools.evidence_store import EvidenceDraft
from deeptrace.tools.scraper.urls import normalize_url_before_fetch


class SqlAlchemyEvidenceStore:
    """Same ingest/versioning semantics as the in-memory adapter, persisted.

    Every record version keeps its own row; ``get``/``get_many`` return the
    record with its body available through ``read_body``. Identical content
    upserts to one active record; changed content supersedes the previous
    version.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def ingest(self, tenant_id: str, draft: EvidenceDraft) -> Evidence:
        if not isinstance(draft, EvidenceDraft):
            raise TypeError("draft must be an EvidenceDraft")
        tenant = _require_identifier("tenant_id", tenant_id)
        if not draft.body:
            raise ValueError("body must be non-empty")

        canonical_url = normalize_url_before_fetch(draft.canonical_url)
        content_hash = _content_hash(draft.body)
        evidence_id = _evidence_id(canonical_url, content_hash)

        async with self._sessions() as session:
            existing = (
                await session.execute(
                    select(EvidenceRecordRow).where(
                        EvidenceRecordRow.tenant_id == tenant,
                        EvidenceRecordRow.evidence_id == evidence_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _to_model(existing)

            prior = (
                await session.execute(
                    select(EvidenceRecordRow)
                    .where(
                        EvidenceRecordRow.tenant_id == tenant,
                        EvidenceRecordRow.canonical_url == canonical_url,
                        EvidenceRecordRow.status == "active",
                    )
                    .order_by(EvidenceRecordRow.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            version = 1
            supersedes = None
            if prior is not None:
                version = prior.version + 1
                supersedes = prior.evidence_id
                prior.status = "superseded"

            record = EvidenceRecordRow(
                tenant_id=tenant,
                evidence_id=evidence_id,
                canonical_url=canonical_url,
                title=draft.title,
                media_type=draft.media_type,
                content_hash=content_hash,
                body=draft.body,
                fetched_at=draft.fetched_at,
                published_at=draft.published_at,
                source_quality=draft.source_quality,
                status="active",
                version=version,
                supersedes=supersedes,
                metadata_json=dict(draft.metadata),
                created_at=datetime.now(UTC),
            )
            session.add(record)
            await session.commit()
            return _to_model(record)

    async def get(self, tenant_id: str, evidence_id: str) -> Evidence:
        async with self._sessions() as session:
            record = (
                await session.execute(
                    select(EvidenceRecordRow).where(
                        EvidenceRecordRow.tenant_id == _require_identifier("tenant_id", tenant_id),
                        EvidenceRecordRow.evidence_id == _require_identifier("evidence_id", evidence_id),
                    )
                )
            ).scalar_one_or_none()
        if record is None:
            raise KeyError("evidence is not available for tenant")
        return _to_model(record)

    async def get_many(
        self, tenant_id: str, evidence_ids: Sequence[str]
    ) -> tuple[Evidence, ...]:
        ids = list(evidence_ids)
        if isinstance(evidence_ids, (str, bytes)):
            raise TypeError("evidence_ids must be a sequence of identifiers")
        results: list[Evidence] = []
        for evidence_id in ids:
            results.append(await self.get(tenant_id, evidence_id))
        return tuple(results)

    async def read_body(self, tenant_id: str, evidence_id: str) -> str:
        async with self._sessions() as session:
            record = (
                await session.execute(
                    select(EvidenceRecordRow).where(
                        EvidenceRecordRow.tenant_id == tenant_id,
                        EvidenceRecordRow.evidence_id == evidence_id,
                    )
                )
            ).scalar_one_or_none()
        if record is None:
            raise KeyError("evidence is not available for tenant")
        return record.body

    async def read_chunks(
        self, tenant_id: str, evidence_id: str
    ) -> tuple[str, ...]:
        body = await self.read_body(tenant_id, evidence_id)
        return (body,) if body else ()

    async def latest_for_source(
        self, tenant_id: str, canonical_url: str
    ) -> Evidence:
        normalized = normalize_url_before_fetch(canonical_url)
        async with self._sessions() as session:
            record = (
                await session.execute(
                    select(EvidenceRecordRow)
                    .where(
                        EvidenceRecordRow.tenant_id == tenant_id,
                        EvidenceRecordRow.canonical_url == normalized,
                        EvidenceRecordRow.status == "active",
                    )
                    .order_by(EvidenceRecordRow.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if record is None:
            raise KeyError("evidence source is not available for tenant")
        return _to_model(record)


def _to_model(record: EvidenceRecordRow) -> Evidence:
    fetched_at = record.fetched_at
    if fetched_at is not None and fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    published_at = record.published_at
    if published_at is not None and published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    return Evidence(
        id=record.evidence_id,
        canonical_url=record.canonical_url,
        title=record.title,
        media_type=record.media_type,
        content_hash=record.content_hash,
        fetched_at=fetched_at,
        published_at=published_at,
        source_quality=record.source_quality,
        status=EvidenceLifecycleStatus.ACTIVE
        if record.status == "active"
        else EvidenceLifecycleStatus.SUPERSEDED,
        version=record.version,
        supersedes=record.supersedes,
        metadata=record.metadata_json or {},
    )


def _require_identifier(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _content_hash(body: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _evidence_id(canonical_url: str, content_hash: str) -> str:
    import hashlib

    payload = f"{canonical_url}\0{content_hash}".encode("utf-8")
    return "evidence-" + hashlib.sha256(payload).hexdigest()
