from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deeptrace.models import RawDocument
from deeptrace.tools.adapters import (
    FetchPageArguments,
    SearchWebArguments,
    _ResearchToolAdapters,
)
from deeptrace.tools.search import ToolContext, search_web
from deeptrace.tools.scraper import WebFetchError


class RaisingFetcher:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls: list[str] = []

    async def fetch(self, url: str) -> RawDocument:
        self.calls.append(url)
        raise self._error


def _adapters(fetcher) -> _ResearchToolAdapters:
    return _ResearchToolAdapters(
        search=lambda query: {"ok": True, "results": []},
        fetcher=fetcher,
        memory=None,
        memory_max_age_days=7,
        now=lambda: datetime(2026, 9, 15, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_fetch_page_preserves_structured_web_error_code() -> None:
    fetcher = RaisingFetcher(
        WebFetchError(
            "insufficient_content",
            "正文未同时达到字符数和 Token 数门槛",
            chars=10,
            tokens=3,
        )
    )
    adapters = _adapters(fetcher)

    result = await adapters.fetch_page(
        FetchPageArguments(url="https://example.com/thin")
    )

    assert result.ok is False
    assert result.error_code == "insufficient_content"
    assert result.message == "正文未同时达到字符数和 Token 数门槛"
    assert fetcher.calls == ["https://example.com/thin"]


@pytest.mark.asyncio
async def test_search_adapter_preserves_provider_error_code() -> None:
    def search(_query: str) -> dict:
        return {
            "ok": False,
            "error": {"code": "http_failed", "message": "Tavily 请求失败：ConnectError"},
        }

    adapters = _ResearchToolAdapters(
        search=search,
        fetcher=RaisingFetcher(RuntimeError("unused")),
        memory=None,
        memory_max_age_days=7,
        now=lambda: datetime(2026, 9, 15, tzinfo=UTC),
    )

    result = await adapters.search_web(SearchWebArguments(query="LangGraph"))

    assert result.ok is False
    assert result.error_code == "http_failed"
    assert result.message == "Tavily 请求失败：ConnectError"


@pytest.mark.asyncio
async def test_unexpected_fetch_exception_is_not_swallowed_by_adapter() -> None:
    fetcher = RaisingFetcher(RuntimeError("scraper exploded"))
    adapters = _adapters(fetcher)

    with pytest.raises(RuntimeError):
        await adapters.fetch_page(
            FetchPageArguments(url="https://example.com/x")
        )


class _RaisingTavily:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def search(self, **_kwargs) -> dict:
        raise self._error


def test_search_provider_timeout_is_classified_as_transient() -> None:
    context = ToolContext(tavily=_RaisingTavily(TimeoutError("timed out")))

    result = search_web(context, "LangGraph")

    assert result["ok"] is False
    assert result["error"]["code"] == "provider_timeout"


def test_search_connection_error_is_classified_as_transient() -> None:
    context = ToolContext(
        tavily=_RaisingTavily(ConnectionError("connection reset by peer"))
    )

    result = search_web(context, "LangGraph")

    assert result["ok"] is False
    assert result["error"]["code"] == "http_failed"


def test_search_unknown_error_stays_recoverable() -> None:
    context = ToolContext(tavily=_RaisingTavily(ValueError("boom")))

    result = search_web(context, "LangGraph")

    assert result["ok"] is False
    assert result["error"]["code"] == "search_failed"
