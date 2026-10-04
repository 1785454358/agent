"""Publisher canonical links must not overwrite distinct retrieved editions."""

from datetime import UTC, datetime

import pytest

from deeptrace.domain import EvidenceLifecycleStatus
from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.tools.adapters import FetchPageArguments
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from tools.test_adapters import _adapters, _context


class PageFetcher:
    def __init__(self, final_url, body):
        self.final_url, self.body = final_url, body

    async def fetch(self, url):
        return RawDocument(
            doc_id="page",
            requested_url=url,
            final_url=self.final_url,
            canonical_url="https://docs.example.org/current/task",
            title="Edition documentation",
            content=self.body,
            content_hash="hash",
            fetched_at=datetime(2026, 10, 4, tzinfo=UTC),
            scraper_used=ScraperUsed.HTTPX_BS4,
            status="success",
        )


async def ingest(store, requested, final, body):
    result = await _adapters(PageFetcher(final, body)).fetch_page(
        FetchPageArguments(url=requested), _context()
    )
    return await store.ingest("tenant", result.evidence)


@pytest.mark.asyncio
async def test_distinct_editions_with_shared_canonical_stay_active():
    store = InMemoryEvidenceStore()
    first = await ingest(
        store,
        "https://docs.example.org/3.11/task",
        "https://docs.example.org/3.11/task",
        "Version 3.11",
    )
    second = await ingest(
        store,
        "https://docs.example.org/zh/3.14/task",
        "https://docs.example.org/zh/3.14/task",
        "Version 3.14",
    )
    assert first.canonical_url == "https://docs.example.org/3.11/task"
    assert second.canonical_url == "https://docs.example.org/zh/3.14/task"
    assert first.id != second.id
    assert (
        await store.get("tenant", first.id)
    ).status is EvidenceLifecycleStatus.ACTIVE
    assert second.status is EvidenceLifecycleStatus.ACTIVE
    assert (
        first.metadata["publisher_canonical_url"]
        == "https://docs.example.org/current/task"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("final", ["https://docs.example.org/3.11/task", ""])
async def test_identity_uses_final_url_with_requested_fallback(final):
    store = InMemoryEvidenceStore()
    record = await ingest(store, "https://docs.example.org/requested", final, "Body")
    assert record.canonical_url == (final or "https://docs.example.org/requested")
    assert record.metadata["final_url"] == final


@pytest.mark.asyncio
async def test_same_actual_url_still_supersedes_and_repeats_are_idempotent():
    store = InMemoryEvidenceStore()
    url = "https://docs.example.org/3.11/task"
    first = await ingest(store, url, url, "Original")
    second = await ingest(store, url, url, "Updated")
    repeat = await ingest(store, url, url, "Updated")
    assert second.canonical_url == url
    assert (
        await store.get("tenant", first.id)
    ).status is EvidenceLifecycleStatus.SUPERSEDED
    assert second.version == 2 and second.supersedes == first.id
    assert repeat.id == second.id and repeat.version == 2
