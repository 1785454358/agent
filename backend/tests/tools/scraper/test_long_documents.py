from io import BytesIO

import httpx
import pytest
from pypdf import PdfReader, PdfWriter

from deeptrace.tools.scraper.fetcher import AsyncWebFetcher
from deeptrace.tools.scraper.pdf import extract_pdf, PdfExtractionError
from deeptrace.tools.evidence_views import select_source_excerpt
from tools.scraper.test_pdf_acquisition import pdf_bytes, public, no_browser


@pytest.mark.asyncio
async def test_plaintext_late_clause_survives_acquisition_and_local_retrieval(monkeypatch):
    clause = 'A client SHOULD NOT automatically retry a non-idempotent request.'
    body = ('Unrelated introductory material.\n\n' * 6000) + '\n9.2.2 Idempotent Methods\n' + clause
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:
        httpx.Response(200, headers={'content-type':'text/plain'}, text=body))) as client:
        fetcher = AsyncWebFetcher(http=client, min_chars=10, min_tokens=1)
        monkeypatch.setattr(fetcher, '_ensure_public_url', public)
        monkeypatch.setattr(fetcher, '_fetch_playwright', no_browser)
        doc = await fetcher.fetch('https://example.com/rfc.txt')
        assert doc.full_content == body
        excerpt = select_source_excerpt(doc.full_content, 'non-idempotent request', 1000)
        assert clause in excerpt.text
        assert any(r.start > 100000 for r in excerpt.ranges)


@pytest.mark.asyncio
async def test_bounded_markup_heavy_document_keeps_late_normative_section(monkeypatch):
    clause = 'A client SHOULD NOT automatically retry a non-idempotent request.'
    html = '<html><title>Normative document</title><body><article>' + (
        '<p class="' + 'layout-' * 120 + '">Introduction to document.</p>') * 3000
    html += '<h2>9.2.2 Idempotent Methods</h2><p>' + clause + '</p></article></body></html>'
    assert len(html) > 2000000
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:
        httpx.Response(200, headers={'content-type':'text/html'}, text=html))) as client:
        fetcher = AsyncWebFetcher(http=client, min_chars=10, min_tokens=1)
        monkeypatch.setattr(fetcher, '_ensure_public_url', public)
        monkeypatch.setattr(fetcher, '_fetch_playwright', no_browser)
        doc = await fetcher.fetch('https://example.com/normative.html')
        assert clause in doc.full_content
        assert clause in select_source_excerpt(doc.full_content, 'non-idempotent', 1000).text


def test_explicit_pdf_page_range_preserves_real_page_numbers_and_omission():
    writer = PdfWriter()
    pages = PdfReader(BytesIO(pdf_bytes())).pages
    for _ in range(60):
        for page in pages:
            writer.add_page(page)
    stream = BytesIO()
    writer.write(stream)
    _, text = extract_pdf(stream.getvalue(), page_start=119, page_end=120)
    assert 'PDF page 119' in text and 'PDF page 120' in text
    assert 'omitted pages: 1-118' in text
    assert 'total pages: 120' in text
    with pytest.raises(PdfExtractionError, match='pdf_page_limit'):
        extract_pdf(stream.getvalue())
