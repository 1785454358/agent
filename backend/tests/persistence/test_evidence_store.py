from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.evidence_store import SqlAlchemyEvidenceStore
from deeptrace.persistence.orm import Base
from deeptrace.tools.evidence_store import EvidenceDraft


async def _make_store(tmp_path):
    engine, sessions = create_session_factory(
        f"sqlite+aiosqlite:///{tmp_path}/evidence.db"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlAlchemyEvidenceStore(sessions)


def _draft(body: str) -> EvidenceDraft:
    return EvidenceDraft(
        canonical_url="https://example.com/a",
        title="来源 A",
        media_type="text/html",
        body=body,
        fetched_at=datetime(2026, 9, 13, tzinfo=UTC),
        source_quality=0.9,
    )


@pytest.mark.asyncio
async def test_evidence_versions_supersede_and_bodies_persist(tmp_path) -> None:
    store = await _make_store(tmp_path)

    first = await store.ingest("tenant-1", _draft("正文版本一"))
    second = await store.ingest("tenant-1", _draft("正文版本二"))
    duplicate = await store.ingest("tenant-1", _draft("正文版本二"))

    assert first.id != second.id
    assert second.version == 2
    assert second.supersedes == first.id
    assert duplicate.id == second.id
    assert (await store.read_body("tenant-1", second.id)) == "正文版本二"
    assert (await store.read_body("tenant-1", first.id)) == "正文版本一"
    latest = await store.latest_for_source("tenant-1", "https://example.com/a")
    assert latest.id == second.id
    with pytest.raises(KeyError):
        await store.get("other-tenant", second.id)


@pytest.mark.asyncio
async def test_evidence_bodies_survive_a_new_store_instance(tmp_path) -> None:
    store = await _make_store(tmp_path)
    evidence = await store.ingest("tenant-1", _draft("重启后仍可读的正文"))

    reopened = await _make_store(tmp_path)
    body = await reopened.read_body("tenant-1", evidence.id)

    assert body == "重启后仍可读的正文"


@pytest.mark.asyncio
async def test_concurrent_different_bodies_keep_every_version(tmp_path) -> None:
    import asyncio

    store = await _make_store(tmp_path)
    draft_a = EvidenceDraft(
        canonical_url="https://example.com/race",
        title="A",
        media_type="text/html",
        body="并发正文 A",
        fetched_at=datetime(2026, 9, 13, tzinfo=UTC),
        source_quality=0.9,
    )
    draft_b = EvidenceDraft(
        canonical_url="https://example.com/race",
        title="B",
        media_type="text/html",
        body="并发正文 B",
        fetched_at=datetime(2026, 9, 13, tzinfo=UTC),
        source_quality=0.9,
    )

    results = await asyncio.gather(
        store.ingest("tenant-1", draft_a), store.ingest("tenant-1", draft_b)
    )
    bodies = {await store.read_body("tenant-1", item.id) for item in results}
    # neither submitted body may be silently dropped
    assert bodies == {"并发正文 A", "并发正文 B"}
    latest = await store.latest_for_source("tenant-1", "https://example.com/race")
    assert await store.read_body("tenant-1", latest.id) in bodies
