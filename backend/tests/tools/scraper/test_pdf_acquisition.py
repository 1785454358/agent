"""PDFs selected from real search use extraction, not HTML browser fallback."""

from io import BytesIO

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from deeptrace.tools.scraper.fetcher import AsyncWebFetcher, WebFetchError
from tools.test_adapters import _adapters, _context
from deeptrace.tools.adapters import FetchPageArguments


def pdf_bytes(*, blank=False, encrypted=False):
    writer = PdfWriter()
    writer.add_metadata({"/Title": "Original reasoning report"})
    for text in ("Published: 5 December 2024. Original research.",
                 "Experimental setup: MODEL_X, MATH, 128 samples. Accuracy is 72 percent."):
        page = writer.add_blank_page(width=600, height=800)
        if not blank:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
                DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(("BT /F1 12 Tf 50 700 Td (" + text + ") Tj ET").encode("ascii"))
            page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("private")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_rotated_arxiv_publication_stamp_is_not_dropped_from_pdf_body():
    from pypdf import PdfReader
    from deeptrace.tools.scraper.pdf import extract_pdf
    writer = PdfWriter()
    page = PdfReader(BytesIO(pdf_bytes())).pages[0]
    stream = page.get_contents()
    stamp = b' BT /F1 12 Tf 0 1 -1 0 30 100 Tm (arXiv:2501.19393v1 [cs.CL] 31 Jan 2025) Tj ET'
    stream.set_data(stream.get_data() + stamp)
    page[NameObject('/Contents')] = stream
    writer.add_page(page)
    buffer = BytesIO()
    writer.write(buffer)
    _, text = extract_pdf(buffer.getvalue())
    assert '31 Jan 2025' in text


async def public(_):
    return None


async def no_browser(_):
    pytest.fail("PDF must not be rendered by the HTML browser fallback")


@pytest.mark.asyncio
async def test_pdf_fetch_and_ingestion_preserve_format_pages_and_full_text(monkeypatch):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, headers={"content-type": "application/pdf"}, content=pdf_bytes()))) as client:
        fetcher = AsyncWebFetcher(http=client, min_chars=10, min_tokens=1, max_page_chars=40)
        monkeypatch.setattr(fetcher, "_ensure_public_url", public)
        monkeypatch.setattr(fetcher, "_fetch_playwright", no_browser)
        try:
            document = await fetcher.fetch("https://example.com/report.pdf")
            assert document.media_type == "application/pdf"
            assert document.scraper_used.value == "httpx_pypdf"
            assert document.title == "Original reasoning report"
            assert "MODEL_X" in document.full_content
            assert "PDF page 2" in document.full_content
            assert len(document.content) <= 40
            result = await _adapters(fetcher).fetch_page(FetchPageArguments(url="https://example.com/report.pdf"), _context())
            assert result.evidence.media_type == "application/pdf"
            assert "MODEL_X" in result.evidence.body
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,code", [
    (b"not a PDF", "invalid_pdf"),
    (pdf_bytes(blank=True), "pdf_text_unavailable"),
    (pdf_bytes(encrypted=True), "pdf_encrypted"),
], ids=["invalid", "image-only", "encrypted"])
async def test_unreadable_pdf_returns_specific_failure_without_browser(monkeypatch, payload, code):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, headers={"content-type": "application/pdf"}, content=payload))) as client:
        fetcher = AsyncWebFetcher(http=client, min_chars=10, min_tokens=1)
        monkeypatch.setattr(fetcher, "_ensure_public_url", public)
        monkeypatch.setattr(fetcher, "_fetch_playwright", no_browser)
        try:
            with pytest.raises(WebFetchError) as caught:
                await fetcher.fetch("https://example.com/report.pdf")
            assert caught.value.code == code
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('limit_kind,code', [('bytes', 'response_too_large'), ('pages', 'pdf_page_limit')])
async def test_pdf_limits_are_explicit_and_never_fall_back_to_browser(monkeypatch, limit_kind, code):
    if limit_kind == 'bytes':
        monkeypatch.setattr('deeptrace.tools.scraper.fetcher.MAX_PDF_RESPONSE_BYTES', 100)
    else:
        monkeypatch.setattr('deeptrace.tools.scraper.pdf.MAX_PDF_PAGES', 1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, headers={'content-type': 'application/pdf'}, content=pdf_bytes()))) as client:
        fetcher = AsyncWebFetcher(http=client, min_chars=10, min_tokens=1)
        monkeypatch.setattr(fetcher, '_ensure_public_url', public)
        monkeypatch.setattr(fetcher, '_fetch_playwright', no_browser)
        try:
            with pytest.raises(WebFetchError) as caught:
                await fetcher.fetch('https://example.com/report.pdf')
            assert caught.value.code == code
        finally:
            await fetcher.aclose()
