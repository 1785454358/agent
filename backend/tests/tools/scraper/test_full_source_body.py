"""Bounded legacy previews must not discard later original evidence."""

import hashlib
from datetime import UTC, datetime

import httpx
import pytest
from tools.test_adapters import _adapters, _context

from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.tools.adapters import FetchPageArguments
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from deeptrace.tools.scraper.fetcher import AsyncWebFetcher


@pytest.mark.asyncio
async def test_fetch_keeps_full_evidence_body_separate_from_bounded_serialized_preview(monkeypatch):
    html = '<html><body><article><h1>Reference manual</h1><p>' + (
        'Ordinary behavior is described in detail for callers and implementers. ' * 50
    ) + '</p><p>LATE_CONDITION: concurrent recovery requires an exclusive lock.</p></article></body></html>'
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"content-type": "text/html"}, text=html),
    )) as client:
        fetcher = AsyncWebFetcher(http=client, max_page_chars=100, min_chars=20, min_tokens=2)
        async def public(_):
            pass
        monkeypatch.setattr(fetcher, "_ensure_public_url", public)
        try:
            document = await fetcher.fetch("https://example.com/reference")
        finally:
            await fetcher.aclose()
    assert len(document.content) == 100
    assert "LATE_CONDITION" in document.full_content
    assert document.content_hash == hashlib.sha256(document.full_content.encode()).hexdigest()
    assert "full_content" not in document.model_dump()
    assert "LATE_CONDITION" not in document.model_dump_json()
    assert "LATE_CONDITION" not in repr(document)


@pytest.mark.asyncio
@pytest.mark.parametrize("full_body", [None, "Opening preview.\n\nLATE_CONDITION: durable storage is required."])
async def test_adapter_persists_full_original_and_legacy_documents_still_work(full_body):
    class Fetcher:
        async def fetch(self, url):
            return RawDocument(
                doc_id="doc", requested_url=url, final_url=url, canonical_url=None,
                title="Manual", content="Opening preview.", full_content=full_body,
                content_hash="unused", fetched_at=datetime.now(UTC),
                scraper_used=ScraperUsed.HTTPX_BS4, status="success",
            )
    result = await _adapters(Fetcher()).fetch_page(
        FetchPageArguments(url="https://example.com/manual"), _context(),
    )
    assert result.evidence.body == (full_body or "Opening preview.")
    assert "LATE_CONDITION" not in result.preview
    store = InMemoryEvidenceStore()
    record = await store.ingest("workspace-1", result.evidence)
    assert await store.read_body("workspace-1", record.id) == (full_body or "Opening preview.")
