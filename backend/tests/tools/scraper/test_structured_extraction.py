"""Catch paragraph corruption and a longer fallback displacing usable text."""

import pytest

from deeptrace.models import ScraperUsed
from deeptrace.tools.scraper.fetcher import AsyncWebFetcher, WebFetchError


def test_inline_api_stays_in_its_conditional_paragraph():
    html = (
        "<main><p>If <code>return_exceptions</code> is false, tasks continue.</p>"
        "<p>Do not swallow cancellation.</p></main>"
    )
    body = AsyncWebFetcher._extract_bs4(html)
    assert "If return_exceptions is false, tasks continue." in body
    assert "\n\n" in body


def test_nested_blocks_are_not_duplicated_and_code_rows_survive():
    html = (
        "<main><section><h2>Cancellation</h2><ul><li>Keep <b>cleanup</b>."
        "<ul><li>Do not suppress errors.</li></ul></li></ul>"
        "<pre><code>try:\n    work()\nfinally:\n    close()</code></pre>"
        "<table><tr><td>State</td><td>Meaning</td></tr></table></section></main>"
    )
    body = AsyncWebFetcher._extract_bs4(html)
    assert "# Cancellation" in body
    assert body.count("Keep cleanup.") == 1
    assert body.count("Do not suppress errors.") == 1
    assert "try:\n    work()\nfinally:\n    close()" in body
    assert "State | Meaning" in body


def test_plain_body_text_is_not_dropped_when_no_paragraph_tags_exist():
    assert AsyncWebFetcher._extract_bs4("<body>Short plain article.</body>") == (
        "Short plain article."
    )


def test_deep_untrusted_markup_does_not_overflow_python_recursion():
    html = (
        "<main>"
        + "<div>" * 1200
        + "<p>Keep the final paragraph.</p>"
        + "</div>" * 1200
        + "</main>"
    )
    assert AsyncWebFetcher._extract_bs4(html) == "Keep the final paragraph."


def test_hidden_comments_are_not_materialized_as_visible_evidence():
    body = AsyncWebFetcher._extract_bs4(
        "<main><!--hidden directive--><p>Visible paragraph.</p></main>"
    )
    assert body == "Visible paragraph."


class StaticHttpFetcher(AsyncWebFetcher):
    def __init__(self, html):
        super().__init__(count_tokens=len, min_chars=10, min_tokens=10)
        self.html = html

    async def _ensure_public_url(self, url):
        # No actual network; the public-URL and SSRF tests exercise those guards.
        return None

    async def _fetch_httpx(self, url):
        return self.html, url

    async def _fetch_playwright(self, url):
        raise WebFetchError("unexpected_browser", "Static HTTP content was usable")


@pytest.mark.asyncio
async def test_extraction_keeps_publication_metadata_even_when_main_text_drops_header(monkeypatch):
    monkeypatch.setattr("deeptrace.tools.scraper.fetcher.extract", lambda *a, **k: "Abstract: measured a new correlation.")
    fetcher = StaticHttpFetcher('<meta name="citation_date" content="2026/09/29"><main><p>Abstract: measured a new correlation.</p></main>')
    try:
        result = await fetcher.fetch("https://example.com/paper")
        assert "Published (HTML metadata): 2026-09-29" in result.content
        assert "Abstract: measured a new correlation." in result.content
    finally:
        await fetcher.aclose()


@pytest.mark.asyncio
async def test_usable_primary_is_not_displaced_by_longer_fallback(monkeypatch):
    primary = "Relevant main text.\n\nA complete condition."
    monkeypatch.setattr(
        "deeptrace.tools.scraper.fetcher.extract", lambda *a, **k: primary
    )
    fetcher = StaticHttpFetcher("<main><p>" + "fallback text " * 300 + "</p></main>")
    try:
        result = await fetcher.fetch("https://example.com/article")
        assert result.content == primary
        assert result.scraper_used is ScraperUsed.HTTPX_TRAFILATURA
        assert result.final_url == "https://example.com/article"
    finally:
        await fetcher.aclose()


@pytest.mark.asyncio
async def test_news_type_and_original_paper_anchor_survive_text_extraction(monkeypatch):
    monkeypatch.setattr('deeptrace.tools.scraper.fetcher.extract', lambda *a, **k: 'A new laboratory result.')
    html = '''<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-06-27"}</script>
        <main><p>A new laboratory result.</p><p>Original publication:
        <a href="https://doi.org/10.1234/new">Read the paper</a></p>
        <section id="references"><a href="https://doi.org/10.1234/old">Old reference</a></section>
        <a href="http://127.0.0.1/secret">Internal</a></main>'''
    fetcher = StaticHttpFetcher(html)
    try:
        result = await fetcher.fetch('https://example.com/news')
        assert 'Source type (HTML metadata): NewsArticle' in result.content
        assert 'Original research links (HTML anchors):\nhttps://doi.org/10.1234/new' in result.content
        assert '10.1234/old' not in result.content
        assert '127.0.0.1' not in result.content
    finally:
        await fetcher.aclose()


@pytest.mark.asyncio
async def test_unusable_primary_uses_structured_fallback_without_browser(monkeypatch):
    monkeypatch.setattr("deeptrace.tools.scraper.fetcher.extract", lambda *a, **k: "")
    fetcher = StaticHttpFetcher(
        "<main><p>Never <code>swallow_errors</code> silently.</p><p>Keep cleanup.</p></main>"
    )
    try:
        result = await fetcher.fetch("https://example.com/article")
        assert "Never swallow_errors silently." in result.content
        assert "\n\n" in result.content
        assert result.scraper_used is ScraperUsed.HTTPX_BS4
    finally:
        await fetcher.aclose()
