from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import threading
import time
from types import SimpleNamespace
from typing import Any

from deeptrace.context import ContextCompressor
from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.orchestration.budget import GlobalBudget
from deeptrace.orchestration.research import ParallelResearchService


class DirectOnlyRuntime:
    def embed(self, texts: list[str]) -> Any:
        raise AssertionError("small test documents must skip embeddings")

    def query_vector(self, query: str) -> Any:
        raise AssertionError("small test documents must skip embeddings")


class SearchStub:
    def __init__(
        self,
        results_by_query: dict[str, list[str | dict[str, Any]] | BaseException],
        *,
        delay: float = 0,
    ) -> None:
        self._results_by_query = results_by_query
        self._delay = delay
        self.calls: list[str] = []
        self._active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def __call__(
        self,
        _tools: object,
        query: str,
        max_results: int = 5,
        target_years: set[int] | None = None,
    ) -> dict[str, Any]:
        del target_years
        with self._lock:
            self.calls.append(query)
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            if self._delay:
                time.sleep(self._delay)
            value = self._results_by_query[query]
            if isinstance(value, BaseException):
                raise value
            return {
                "ok": True,
                "query": query,
                "results": [
                    (
                        dict(item)
                        if isinstance(item, dict)
                        else {"title": f"title-{index}", "url": item, "snippet": ""}
                    )
                    for index, item in enumerate(value[:max_results])
                ],
            }
        finally:
            with self._lock:
                self._active -= 1


class CountingFetcher:
    def __init__(self, *, failures: set[str] | None = None, delay: float = 0) -> None:
        self.calls: list[str] = []
        self.failures = failures or set()
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def fetch(self, url: str) -> RawDocument:
        self.calls.append(url)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if url in self.failures:
                raise RuntimeError("fetch exploded")
            slug = url.rsplit("/", 1)[-1]
            return make_document(url, slug)
        finally:
            self.active -= 1


def make_document(url: str, marker: str) -> RawDocument:
    return RawDocument(
        doc_id=f"doc-{marker}",
        requested_url=url,
        final_url=url,
        canonical_url=url,
        title=f"Title {marker}",
        content=f"Content {marker}",
        content_hash=f"hash-{marker}",
        fetched_at=datetime.now(UTC),
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )


def make_settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "max_search_results_per_query": 5,
        "scraper_concurrency": 15,
        "context_max_results": 10,
        "max_fetched_pages": 20,
        "max_runtime_seconds": 300,
        "max_total_tokens": 0,
        "max_cost_usd": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_service(
    results_by_query: dict[
        str, list[str | dict[str, Any]] | BaseException
    ],
    *,
    search_delay: float = 0,
    fetch_delay: float = 0,
    failures: set[str] | None = None,
    settings: SimpleNamespace | None = None,
    budget: GlobalBudget | None = None,
) -> tuple[ParallelResearchService, SearchStub, CountingFetcher]:
    search = SearchStub(results_by_query, delay=search_delay)
    fetcher = CountingFetcher(failures=failures, delay=fetch_delay)
    service = ParallelResearchService(
        tools=object(),
        fetcher=fetcher,
        compressor=ContextCompressor(DirectOnlyRuntime()),
        settings=settings or make_settings(),
        budget=budget,
        search=search,
    )
    return service, search, fetcher


def test_collect_runs_all_query_searches_concurrently() -> None:
    service, search, _fetcher = make_service(
        {"a": ["https://e.test/a"], "b": ["https://e.test/b"]},
        search_delay=0.05,
    )

    _context, _documents, sources, results = asyncio.run(
        service.acollect("root", ["a", "b"], None)
    )

    assert search.max_active == 2
    assert [item.query for item in results] == ["a", "b"]
    assert sources == ["https://e.test/a", "https://e.test/b"]


def test_collect_claims_duplicate_urls_once_after_search() -> None:
    service, _search, fetcher = make_service(
        {
            "a": ["https://e.test/shared?utm_source=a"],
            "b": ["https://e.test/shared?utm_source=b"],
        }
    )

    _context, _documents, _sources, results = asyncio.run(
        service.acollect("root", ["a", "b"], None)
    )

    assert fetcher.calls == ["https://e.test/shared"]
    assert [[doc.final_url for doc in item.documents] for item in results] == [
        ["https://e.test/shared"],
        ["https://e.test/shared"],
    ]


def test_collect_reuses_initial_search_for_original_question() -> None:
    service, search, fetcher = make_service(
        {"generated": ["https://e.test/generated"]}
    )
    initial = {
        "ok": True,
        "query": "root",
        "results": [
            {"title": "root", "url": "https://e.test/root", "snippet": ""}
        ],
    }

    _context, _documents, sources, results = asyncio.run(
        service.acollect("root", ["generated", "root"], initial)
    )

    assert search.calls == ["generated"]
    assert fetcher.calls == ["https://e.test/generated", "https://e.test/root"]
    assert sources == ["https://e.test/generated", "https://e.test/root"]
    assert [item.candidate_count for item in results] == [1, 1]


def test_collect_reuses_initial_search_after_question_normalization() -> None:
    service, search, _fetcher = make_service({})
    initial = {
        "ok": True,
        "query": "人工 智能",
        "results": [
            {"title": "root", "url": "https://e.test/root", "snippet": ""}
        ],
    }

    _context, _documents, sources, _results = asyncio.run(
        service.acollect("人工 智能", ["人工智能"], initial)
    )

    assert search.calls == []
    assert sources == ["https://e.test/root"]


def test_search_provided_raw_content_skips_fetch() -> None:
    service, _search, fetcher = make_service(
        {
            "root": [
                {
                    "title": "provider page",
                    "url": "https://e.test/provider",
                    "snippet": "summary",
                    "raw_content": "provider supplied full content",
                }
            ]
        }
    )

    context, documents, sources, results = asyncio.run(
        service.acollect("root", ["root"], None)
    )

    assert fetcher.calls == []
    assert sources == ["https://e.test/provider"]
    assert "Content: provider supplied full content" in context
    assert list(documents.values())[0].content == "provider supplied full content"
    assert results[0].fetch_success_count == 1


def test_expired_budget_starts_no_initial_or_parallel_search() -> None:
    settings = make_settings(max_runtime_seconds=1)
    budget = GlobalBudget(settings, datetime.now(UTC) - timedelta(seconds=2))
    service, search, _fetcher = make_service(
        {"root": ["https://e.test/root"]}, settings=settings, budget=budget
    )

    initial = asyncio.run(service.asearch_initial("root"))
    context, documents, sources, results = asyncio.run(
        service.acollect("root", ["root"], None)
    )

    assert search.calls == []
    assert initial["error"]["code"] == "time_budget"
    assert context == ""
    assert documents == {}
    assert sources == []
    assert results[0].errors == ["time_budget"]


def test_async_search_is_bounded_by_remaining_deadline() -> None:
    class HangingAsyncSearch:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def __call__(self, *_args: object) -> dict[str, Any]:
            self.started.set()
            await asyncio.sleep(60)
            raise AssertionError("deadline should cancel this search")

    async def run() -> tuple[dict[str, Any], float]:
        settings = make_settings(max_runtime_seconds=0.02)
        budget = GlobalBudget(settings, datetime.now(UTC))
        search = HangingAsyncSearch()
        service = ParallelResearchService(
            tools=object(),
            fetcher=CountingFetcher(),
            compressor=ContextCompressor(DirectOnlyRuntime()),
            settings=settings,
            budget=budget,
            search=search,
        )
        started = time.perf_counter()
        payload = await service.asearch_initial("root")
        return payload, time.perf_counter() - started

    payload, elapsed = asyncio.run(run())

    assert payload["error"]["code"] == "time_budget"
    assert elapsed < 0.2


def test_fetch_is_bounded_by_remaining_deadline() -> None:
    async def run():
        settings = make_settings(max_runtime_seconds=0.02)
        budget = GlobalBudget(settings, datetime.now(UTC))
        service, _search, _fetcher = make_service(
            {"a": ["https://e.test/slow"]},
            fetch_delay=60,
            settings=settings,
            budget=budget,
        )
        return await asyncio.wait_for(
            service.acollect("root", ["a"], None), timeout=0.2
        )

    _context, documents, sources, results = asyncio.run(run())

    assert documents == {}
    assert sources == []
    assert results[0].errors == ["time_budget"]


def test_context_filter_is_bounded_by_remaining_deadline() -> None:
    class HangingCompressor:
        async def aget_context(self, *_args, **_kwargs):
            await asyncio.sleep(60)

    async def run():
        settings = make_settings(max_runtime_seconds=0.02)
        budget = GlobalBudget(settings, datetime.now(UTC))
        service = ParallelResearchService(
            tools=object(),
            fetcher=CountingFetcher(),
            compressor=HangingCompressor(),
            settings=settings,
            budget=budget,
            search=SearchStub(
                {
                    "a": [
                        {
                            "title": "provider",
                            "url": "https://e.test/provider",
                            "raw_content": "full content",
                        }
                    ]
                }
            ),
        )
        return await asyncio.wait_for(
            service.acollect("root", ["a"], None), timeout=0.2
        )

    context, _documents, _sources, results = asyncio.run(run())

    assert context == ""
    assert results[0].errors == ["time_budget"]


def test_collect_uses_one_shared_fetch_semaphore() -> None:
    settings = make_settings(scraper_concurrency=2)
    service, _search, fetcher = make_service(
        {"a": [f"https://e.test/{index}" for index in range(5)]},
        fetch_delay=0.01,
        settings=settings,
    )

    asyncio.run(service.acollect("root", ["a"], None))

    assert fetcher.max_active == 2


def test_cached_pages_do_not_consume_network_page_budget() -> None:
    settings = make_settings(max_fetched_pages=1)
    budget = GlobalBudget(settings, datetime.now(UTC))
    service, _search, fetcher = make_service(
        {
            "a": [
                "https://e.test/cached",
                "https://e.test/network",
                "https://e.test/skipped",
            ]
        },
        settings=settings,
        budget=budget,
    )
    service.cache_documents([make_document("https://e.test/cached", "cached")])

    _context, documents, sources, results = asyncio.run(
        service.acollect("root", ["a"], None)
    )

    assert fetcher.calls == ["https://e.test/network"]
    assert budget.pages_used == 1
    assert set(documents) == {"doc-cached", "doc-network"}
    assert sources == ["https://e.test/cached", "https://e.test/network"]
    assert results[0].fetch_success_count == 2
    assert results[0].fetch_failure_count == 1
    assert results[0].errors == ["page_budget"]


def test_collect_preserves_successful_queries_when_siblings_fail() -> None:
    service, _search, _fetcher = make_service(
        {
            "search-fails": RuntimeError("search exploded"),
            "partial": ["https://e.test/good", "https://e.test/bad"],
        },
        failures={"https://e.test/bad"},
    )

    context, documents, sources, results = asyncio.run(
        service.acollect("root", ["search-fails", "partial"], None)
    )

    assert "Content good" in context
    assert set(documents) == {"doc-good"}
    assert sources == ["https://e.test/good"]
    assert results[0].errors == ["search_failed"]
    assert results[1].fetch_success_count == 1
    assert results[1].fetch_failure_count == 1
    assert results[1].errors == ["fetch_failed"]


def test_initial_search_uses_the_configured_result_limit() -> None:
    service, search, _fetcher = make_service(
        {"root": [f"https://e.test/{index}" for index in range(8)]},
        settings=make_settings(max_search_results_per_query=3),
    )

    payload = asyncio.run(service.asearch_initial("root"))

    assert search.calls == ["root"]
    assert [item["url"] for item in payload["results"]] == [
        "https://e.test/0",
        "https://e.test/1",
        "https://e.test/2",
    ]
