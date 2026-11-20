import httpx
import pytest
from deeptrace.tools.scraper.fetcher import AsyncWebFetcher
from tools.scraper.test_pdf_acquisition import public, no_browser


@pytest.mark.asyncio
async def test_observed_trailing_slash_redirect_is_not_normalized_back_into_loop(monkeypatch):
    def serve(request):
        if request.url.path == '/info/document':
            return httpx.Response(301, headers={'location':'/info/document/'})
        assert request.url.path == '/info/document/'
        return httpx.Response(200, headers={'content-type':'text/html'},
            text='<html><title>Document</title><article><p>Original normative text.</p></article></html>')
    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        fetcher = AsyncWebFetcher(http=client, min_chars=10, min_tokens=1)
        monkeypatch.setattr(fetcher,'_ensure_public_url',public)
        monkeypatch.setattr(fetcher,'_fetch_playwright',no_browser)
        doc = await fetcher.fetch('https://example.com/info/document')
        assert 'Original normative text.' in doc.full_content
