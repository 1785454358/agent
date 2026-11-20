"""Usable prose must not hide lost technical lists, tables or main code."""

import pytest
from tools.scraper.test_structured_extraction import StaticHttpFetcher

from deeptrace.models import ScraperUsed


@pytest.mark.asyncio
async def test_article_retains_list_conditions_and_table_rows():
    html = (
        '<html><body><div class="content"><h1>Journal modes</h1><p>'
        + 'The journal retains a consistent generation for active sessions. ' * 15
        + '</p><p>There are several restrictions:</p><ol>'
        '<li>All sessions must share a local host; remote filesystems are unsupported.</li>'
        '<li>Changing the block size requires returning to the legacy journal mode.</li>'
        '</ol><table><tr><th>Mode</th><th>Readers</th></tr>'
        '<tr><td>Snapshot</td><td>Keep the old generation until release.</td></tr></table>'
        '<p>' + 'The application controls the lifetime of each session. ' * 15
        + '</p></div></body></html>'
    )
    fetcher = StaticHttpFetcher(html)
    try:
        result = await fetcher.fetch('https://example.com/journals')
        assert 'remote filesystems are unsupported' in result.full_content
        assert 'Changing the block size' in result.full_content
        assert 'Keep the old generation until release.' in result.full_content
    finally:
        await fetcher.aclose()


@pytest.mark.asyncio
async def test_missing_main_code_selects_structured_fallback(monkeypatch):
    primary = 'This client can be used in isolation.\n\nA combined example follows.'
    monkeypatch.setattr('deeptrace.tools.scraper.fetcher.extract', lambda *a, **k: primary)
    fetcher = StaticHttpFetcher(
        '<main><p>This client can be used in isolation.</p>'
        '<pre><code>client = MemoryClient()\nclient.put("key", value)</code></pre>'
        '<p>A combined example follows.</p></main>'
    )
    try:
        result = await fetcher.fetch('https://example.com/client')
        assert 'client = MemoryClient()\nclient.put("key", value)' in result.full_content
        assert result.scraper_used is ScraperUsed.HTTPX_BS4
    finally:
        await fetcher.aclose()


@pytest.mark.asyncio
async def test_navigation_code_does_not_displace_valid_primary(monkeypatch):
    primary = 'Main prose is complete and relevant to the article.'
    monkeypatch.setattr('deeptrace.tools.scraper.fetcher.extract', lambda *a, **k: primary)
    fetcher = StaticHttpFetcher(
        '<nav><pre>install_unrelated_navigation_plugin()</pre></nav>'
        '<main><p>' + primary + '</p><p>' + 'footer-like noise ' * 100 + '</p></main>'
    )
    try:
        result = await fetcher.fetch('https://example.com/article')
        assert result.full_content == primary
        assert result.scraper_used is ScraperUsed.HTTPX_TRAFILATURA
    finally:
        await fetcher.aclose()


@pytest.mark.asyncio
async def test_equivalent_markdown_code_does_not_force_fallback(monkeypatch):
    primary = 'Main prose.\n\n```python\nclient = MemoryClient()\n```'
    monkeypatch.setattr('deeptrace.tools.scraper.fetcher.extract', lambda *a, **k: primary)
    fetcher = StaticHttpFetcher('<main><p>Main prose.</p><pre>client = MemoryClient()</pre></main>')
    try:
        result = await fetcher.fetch('https://example.com/article')
        assert result.full_content == primary
    finally:
        await fetcher.aclose()
