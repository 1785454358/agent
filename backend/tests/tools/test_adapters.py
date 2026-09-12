from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from deeptrace.domain import ToolName
from deeptrace.memory import MemoryEntry
from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.tools.adapters import (
    FetchPageArguments,
    SearchMemoryArguments,
    SearchWebArguments,
    build_research_tool_registry,
)


NOW = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


class FetcherStub:
    def __init__(self, document: RawDocument) -> None:
        self.document = document
        self.calls: list[str] = []

    async def fetch(self, url: str) -> RawDocument:
        self.calls.append(url)
        return self.document


class MemoryStub:
    def __init__(self, entries: list[MemoryEntry]) -> None:
        self._entries = entries

    def entries(self) -> list[MemoryEntry]:
        return list(self._entries)


def _document(*, body: str = "full page body") -> RawDocument:
    return RawDocument(
        doc_id="doc-1",
        requested_url="https://example.com/requested",
        final_url="https://example.com/final",
        canonical_url="https://example.com/article",
        title="Article",
        content=body,
        content_hash="hash-1",
        fetched_at=NOW,
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
        source_published_at=NOW - timedelta(days=1),
        publisher="Example",
    )


def _memory_entry(
    *, title: str, age_days: int, url: str
) -> MemoryEntry:
    return MemoryEntry(
        url=url,
        title=title,
        content="memory body " * 100,
        content_hash=f"hash-{age_days}",
        published_at=None,
        fetched_at=NOW - timedelta(days=age_days),
    )


@pytest.mark.asyncio
async def test_builder_registers_exactly_three_normalized_atomic_tools() -> None:
    calls: list[str] = []

    def search(query: str) -> dict:
        calls.append(query)
        return {
            "ok": True,
            "results": [
                {
                    "url": "https://EXAMPLE.com/a/?utm_source=test",
                    "title": "A" * 500,
                    "snippet": "S" * 1_000,
                    "raw_content": "must not cross adapter boundary",
                }
            ],
        }

    registry = build_research_tool_registry(
        search=search,
        fetcher=FetcherStub(_document()),
        memory=None,
        now=lambda: NOW,
    )

    assert registry.names() == (
        ToolName.SEARCH_WEB,
        ToolName.FETCH_PAGE,
        ToolName.SEARCH_MEMORY,
    )
    spec = registry.resolve(ToolName.SEARCH_WEB)
    result = await spec.handler(SearchWebArguments(query="  Harness  ", limit=3))
    payload = json.loads(result.preview)

    assert result.ok
    assert calls == ["Harness"]
    assert payload == {
        "results": [
            {
                "url": "https://example.com/a",
                "title": "A" * 300,
                "snippet": "S" * 500,
            }
        ]
    }
    assert "raw_content" not in result.preview


@pytest.mark.asyncio
async def test_fetch_adapter_converts_raw_document_to_evidence_draft() -> None:
    fetcher = FetcherStub(_document(body="evidence body"))
    registry = build_research_tool_registry(
        search=lambda _query: {"ok": True, "results": []},
        fetcher=fetcher,
        memory=None,
        now=lambda: NOW,
    )

    result = await registry.resolve(ToolName.FETCH_PAGE).handler(
        FetchPageArguments(url="https://example.com/requested")
    )

    assert result.ok and result.evidence is not None
    assert result.evidence.canonical_url == "https://example.com/article"
    assert result.evidence.body == "evidence body"
    assert result.evidence.title == "Article"
    assert result.evidence.metadata["publisher"] == "Example"
    assert fetcher.calls == ["https://example.com/requested"]


@pytest.mark.asyncio
async def test_memory_adapter_filters_expired_entries_and_never_returns_body() -> None:
    memory = MemoryStub(
        [
            _memory_entry(
                title="LangGraph checkpoint",
                age_days=1,
                url="https://example.com/fresh",
            ),
            _memory_entry(
                title="LangGraph old",
                age_days=30,
                url="https://example.com/old",
            ),
        ]
    )
    registry = build_research_tool_registry(
        search=lambda _query: {"ok": True, "results": []},
        fetcher=FetcherStub(_document()),
        memory=memory,
        memory_max_age_days=7,
        now=lambda: NOW,
    )

    result = await registry.resolve(ToolName.SEARCH_MEMORY).handler(
        SearchMemoryArguments(query="LangGraph", limit=3)
    )
    payload = json.loads(result.preview)

    assert result.ok
    assert [item["url"] for item in payload["results"]] == [
        "https://example.com/fresh"
    ]
    assert "memory body " * 2 not in result.preview


@pytest.mark.asyncio
async def test_known_dependency_failures_become_stable_adapter_errors() -> None:
    def failed_search(_query: str) -> dict:
        return {"ok": False, "error": {"code": "provider-secret-detail"}}

    registry = build_research_tool_registry(
        search=failed_search,
        fetcher=FetcherStub(_document()),
        memory=None,
        now=lambda: NOW,
    )

    search_result = await registry.resolve(ToolName.SEARCH_WEB).handler(
        SearchWebArguments(query="query")
    )
    memory_result = await registry.resolve(ToolName.SEARCH_MEMORY).handler(
        SearchMemoryArguments(query="query")
    )

    assert not search_result.ok and search_result.error_code == "search_failed"
    assert not memory_result.ok and memory_result.error_code == "memory_disabled"
    assert "secret" not in repr(search_result)
