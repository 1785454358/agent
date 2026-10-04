import pytest

from deeptrace.tools.scraper import (
    ExtractionCandidate,
    is_allowed_dns_resolution,
    is_usable_text,
    select_best_extraction,
)
from deeptrace.models import ScraperUsed
from deeptrace.tools.scraper.urls import validate_public_url


@pytest.mark.asyncio
async def test_http_failure_is_not_lost_when_browser_fallback_also_fails(monkeypatch):
    import httpx
    from deeptrace.tools.scraper.fetcher import AsyncWebFetcher, WebFetchError

    async def public(_):
        return None

    async def browser(_):
        raise WebFetchError("browser_failed", "浏览器抓取失败：TimeoutError")

    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(403, request=request)
    )) as client:
        fetcher = AsyncWebFetcher(http=client)
        monkeypatch.setattr(fetcher, "_ensure_public_url", public)
        monkeypatch.setattr(fetcher, "_fetch_playwright", browser)
        with pytest.raises(WebFetchError) as caught:
            await fetcher.fetch("https://example.com/blocked")
        assert caught.value.code == "browser_failed"
        assert "403" in str(caught.value)
        assert "TimeoutError" in str(caught.value)
        await fetcher.aclose()


@pytest.mark.asyncio
async def test_browser_waits_once_if_navigation_interrupts_content_read():
    from deeptrace.tools.scraper.fetcher import AsyncWebFetcher

    class Page:
        reads = 0
        waits = 0

        async def content(self):
            self.reads += 1
            if self.reads == 1:
                raise RuntimeError("Page.content: Unable to retrieve content because the page is navigating and changing the content.")
            return "<html>article</html>"

        async def wait_for_load_state(self, state, *, timeout):
            assert state == "domcontentloaded"
            assert timeout == 15000
            self.waits += 1

    fetcher = AsyncWebFetcher()
    page = Page()
    try:
        assert await fetcher._read_browser_content(page) == "<html>article</html>"
        assert page.reads == 2
        assert page.waits == 1
    finally:
        await fetcher.aclose()


def test_text_must_pass_both_quality_minimums() -> None:
    assert not is_usable_text("字" * 600, lambda _: 150, 500, 200)
    assert is_usable_text("字" * 600, lambda _: 220, 500, 200)


def test_fallback_selects_best_text_and_records_its_scraper() -> None:
    candidates = [
        ExtractionCandidate(
            text="短" * 300,
            title="HTTPX Trafilatura",
            scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
            source_url="https://example.com/news",
        ),
        ExtractionCandidate(
            text="长" * 700,
            title="Playwright BS4",
            scraper_used=ScraperUsed.PLAYWRIGHT_BS4,
            source_url="https://example.com/news",
        ),
    ]

    selected = select_best_extraction(candidates)

    assert selected.text == "长" * 700
    assert selected.scraper_used is ScraperUsed.PLAYWRIGHT_BS4


def test_benchmark_dns_proxy_requires_explicit_opt_in() -> None:
    """受控沙箱可放行域名代理地址，但字面量非公网 IP 始终被拒绝。"""
    assert not is_allowed_dns_resolution("198.18.0.12", False)
    assert is_allowed_dns_resolution("198.18.0.12", True)
    assert not is_allowed_dns_resolution("10.0.0.1", True)
    assert validate_public_url("https://198.18.0.12/news")[0] is False
