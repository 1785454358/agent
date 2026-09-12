from datetime import UTC, datetime

import pytest

from deeptrace.domain import EvidenceLifecycleStatus
from deeptrace.tools.evidence_store import EvidenceDraft, InMemoryEvidenceStore


def _draft(*, url: str = "https://EXAMPLE.com/research/?utm_source=test", body: str = "body") -> EvidenceDraft:
    return EvidenceDraft(
        canonical_url=url,
        title="Research source",
        media_type="text/html",
        body=body,
        fetched_at=datetime(2026, 9, 12, 8, 0, tzinfo=UTC),
        published_at=datetime(2026, 9, 11, 8, 0, tzinfo=UTC),
        source_quality=0.9,
        metadata={"language": "en"},
    )


@pytest.mark.asyncio
async def test_identical_normalized_content_upserts_one_active_record() -> None:
    store = InMemoryEvidenceStore()

    first = await store.ingest("tenant-a", _draft())
    second = await store.ingest(
        "tenant-a",
        _draft(url="https://example.com/research", body="body"),
    )

    assert second == first
    assert first.canonical_url == "https://example.com/research"
    assert first.status is EvidenceLifecycleStatus.ACTIVE
    assert first.version == 1
    assert await store.read_body("tenant-a", first.id) == "body"


@pytest.mark.asyncio
async def test_changed_content_creates_version_and_supersedes_prior_record() -> None:
    store = InMemoryEvidenceStore()
    first = await store.ingest("tenant-a", _draft(body="first"))

    second = await store.ingest("tenant-a", _draft(body="second"))

    assert second.id != first.id
    assert second.version == 2
    assert second.supersedes == first.id
    assert second.status is EvidenceLifecycleStatus.ACTIVE
    old = await store.get("tenant-a", first.id)
    assert old.status is EvidenceLifecycleStatus.SUPERSEDED
    assert await store.read_body("tenant-a", old.id) == "first"
    assert await store.latest_for_source("tenant-a", second.canonical_url) == second


@pytest.mark.asyncio
async def test_reads_preserve_order_and_enforce_tenant_boundaries() -> None:
    store = InMemoryEvidenceStore()
    first = await store.ingest(
        "tenant-a", _draft(url="https://example.com/one", body="one")
    )
    second = await store.ingest(
        "tenant-a", _draft(url="https://example.com/two", body="two")
    )

    records = await store.get_many("tenant-a", [second.id, first.id, second.id])

    assert [record.id for record in records] == [second.id, first.id, second.id]
    with pytest.raises(KeyError, match="evidence is not available"):
        await store.get("tenant-b", first.id)
    with pytest.raises(KeyError, match="evidence is not available"):
        await store.read_body("tenant-b", first.id)


@pytest.mark.asyncio
async def test_body_is_bounded_and_stored_as_bounded_chunks() -> None:
    store = InMemoryEvidenceStore(max_body_bytes=20, max_chunk_bytes=5)
    record = await store.ingest("tenant-a", _draft(body="abcdefghijkl"))

    chunks = await store.read_chunks("tenant-a", record.id)

    assert chunks == ("abcde", "fghij", "kl")
    assert all(len(chunk.encode("utf-8")) <= 5 for chunk in chunks)
    with pytest.raises(ValueError, match="body exceeds 20 encoded bytes"):
        await store.ingest("tenant-a", _draft(body="x" * 21))


@pytest.mark.asyncio
async def test_tenant_and_body_inputs_are_validated_before_storage() -> None:
    store = InMemoryEvidenceStore()

    with pytest.raises(ValueError, match="tenant_id must be a non-empty string"):
        await store.ingest(" ", _draft())
    with pytest.raises(ValueError, match="body must be non-empty"):
        await store.ingest("tenant-a", _draft(body=""))
