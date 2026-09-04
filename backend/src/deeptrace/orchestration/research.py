"""One-pass parallel search, fetch, and direct context collection."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import inspect
import re
from typing import Any

from deeptrace.context import ContextCompressor
from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.orchestration.budget import GlobalBudget
from deeptrace.tools import ToolContext, search_web
from deeptrace.tools.scraper import AsyncWebFetcher, WebFetchError, normalize_url_before_fetch


JsonObject = dict[str, Any]
SearchFunction = Callable[
    [ToolContext, str, int, set[int] | None], Any
]


def _query_key(value: str) -> str:
    """比较查询身份时忽略大小写及空白，避免原问题被重复搜索。"""
    return re.sub(r"\s+", "", value).casefold()


def _budget_error() -> JsonObject:
    return {
        "ok": False,
        "error": {
            "code": "time_budget",
            "message": "研究运行时间预算已耗尽",
            "details": {},
        },
    }


@dataclass(frozen=True, slots=True)
class QueryResearchResult:
    """Operational result for one query; it is not persisted as research evidence."""

    query: str
    context: str
    sources: list[str]
    documents: list[RawDocument]
    candidate_count: int
    fetch_success_count: int
    fetch_failure_count: int
    errors: list[str]


class ParallelResearchService:
    """Collect all query context in one bounded parallel fan-out/fan-in pass."""

    def __init__(
        self,
        *,
        tools: ToolContext,
        fetcher: AsyncWebFetcher,
        compressor: ContextCompressor,
        settings: Any,
        budget: GlobalBudget | None = None,
        search: SearchFunction = search_web,
    ) -> None:
        self._tools = tools
        self._fetcher = fetcher
        self._compressor = compressor
        self._settings = settings
        self._budget = budget
        self._search = search
        self._fetch_semaphore = asyncio.Semaphore(
            max(1, int(getattr(settings, "scraper_concurrency", 15)))
        )
        self._document_cache: dict[str, RawDocument] = {}

    def cache_documents(self, documents: Sequence[RawDocument]) -> None:
        """Seed the page cache, typically with documents restored from Memory."""
        for document in documents:
            self._cache_document(document)

    async def asearch_initial(self, question: str) -> JsonObject:
        """Run the single initial search used as input to query planning."""
        return await self._search_one(question)

    async def acollect(
        self,
        question: str,
        queries: Sequence[str],
        initial_search: Mapping[str, Any] | None,
    ) -> tuple[str, dict[str, RawDocument], list[str], list[QueryResearchResult]]:
        """Search all queries, fetch each URL once, and build Writer-ready context."""
        ordered_queries = [str(query).strip() for query in queries]
        if self._budget is not None and self._budget.stop_reason(
            datetime.now(UTC)
        ) is not None:
            results = [
                QueryResearchResult(
                    query=query,
                    context="",
                    sources=[],
                    documents=[],
                    candidate_count=0,
                    fetch_success_count=0,
                    fetch_failure_count=0,
                    errors=[self._budget.reason or "time_budget"],
                )
                for query in ordered_queries
            ]
            return "", {}, [], results
        search_payloads = await asyncio.gather(
            *(
                self._reuse_or_search(question, query, initial_search)
                for query in ordered_queries
            ),
            return_exceptions=True,
        )

        query_urls: list[list[str]] = [[] for _query in ordered_queries]
        query_errors: list[list[str]] = [[] for _query in ordered_queries]
        candidate_counts = [0 for _query in ordered_queries]
        claimed_urls: list[str] = []
        globally_claimed: set[str] = set()
        provided_documents: dict[str, RawDocument] = {}

        for query_index, payload in enumerate(search_payloads):
            if isinstance(payload, BaseException):
                query_errors[query_index].append("search_failed")
                continue
            if not payload.get("ok"):
                query_errors[query_index].append(self._payload_error_code(payload))
                continue
            raw_results = payload.get("results", [])
            if not isinstance(raw_results, list):
                query_errors[query_index].append("search_failed")
                continue
            candidate_counts[query_index] = len(raw_results)
            seen_in_query: set[str] = set()
            for item in raw_results:
                url = str(item.get("url", "")) if isinstance(item, Mapping) else ""
                try:
                    normalized = normalize_url_before_fetch(url)
                except ValueError:
                    query_errors[query_index].append("invalid_url")
                    continue
                if normalized in seen_in_query:
                    continue
                seen_in_query.add(normalized)
                query_urls[query_index].append(normalized)
                raw_content = item.get("raw_content") if isinstance(item, Mapping) else None
                if isinstance(raw_content, str) and raw_content.strip():
                    provided_documents.setdefault(
                        normalized,
                        self._document_from_search_result(
                            normalized, item, raw_content.strip()
                        ),
                    )
                if normalized not in globally_claimed:
                    globally_claimed.add(normalized)
                    claimed_urls.append(normalized)

        for normalized, document in provided_documents.items():
            self._cache_document(document, requested_alias=normalized)
        fetch_errors = await self._fetch_claimed_urls(claimed_urls)

        documents_by_query: list[list[RawDocument]] = []
        for query_index, urls in enumerate(query_urls):
            documents: list[RawDocument] = []
            seen_documents: set[str] = set()
            for url in urls:
                document = self._document_cache.get(url)
                if document is None:
                    query_errors[query_index].append(
                        fetch_errors.get(url, "fetch_failed")
                    )
                    continue
                if document.doc_id in seen_documents:
                    continue
                seen_documents.add(document.doc_id)
                documents.append(document)
            documents_by_query.append(documents)

        context_values = await asyncio.gather(
            *(
                self._compressor.aget_context(
                    query,
                    documents,
                    max_results=int(getattr(self._settings, "context_max_results", 10)),
                )
                for query, documents in zip(
                    ordered_queries, documents_by_query, strict=True
                )
            ),
            return_exceptions=True,
        )

        results: list[QueryResearchResult] = []
        collected_documents: dict[str, RawDocument] = {}
        sources: list[str] = []
        seen_sources: set[str] = set()
        contexts: list[str] = []
        for index, (query, documents, context_value) in enumerate(
            zip(ordered_queries, documents_by_query, context_values, strict=True)
        ):
            if isinstance(context_value, BaseException):
                query_errors[index].append("context_failed")
                context = ""
            else:
                context = context_value.strip()
            if context:
                contexts.append(context)
            query_sources: list[str] = []
            for document in documents:
                collected_documents.setdefault(document.doc_id, document)
                source = document.final_url or document.requested_url
                query_sources.append(source)
                if source not in seen_sources:
                    seen_sources.add(source)
                    sources.append(source)
            fetch_failures = sum(
                1 for url in query_urls[index] if self._document_cache.get(url) is None
            ) + query_errors[index].count("invalid_url")
            results.append(
                QueryResearchResult(
                    query=query,
                    context=context,
                    sources=query_sources,
                    documents=documents,
                    candidate_count=candidate_counts[index],
                    fetch_success_count=len(documents),
                    fetch_failure_count=fetch_failures,
                    errors=query_errors[index],
                )
            )

        return "\n\n".join(contexts), collected_documents, sources, results

    async def _reuse_or_search(
        self,
        question: str,
        query: str,
        initial_search: Mapping[str, Any] | None,
    ) -> JsonObject:
        if initial_search is not None and _query_key(query) == _query_key(question):
            return dict(initial_search)
        return await self._search_one(query)

    async def _search_one(self, query: str) -> JsonObject:
        timeout: float | None = None
        if self._budget is not None:
            timeout = self._budget.remaining_seconds(datetime.now(UTC))
            if timeout <= 0:
                return _budget_error()
        try:
            operation = self._invoke_search(query)
            return await asyncio.wait_for(
                operation,
                timeout=timeout,
            )
        except TimeoutError:
            if self._budget is not None:
                self._budget.stop_reason(datetime.now(UTC))
            return _budget_error()
        except Exception:
            return {
                "ok": False,
                "error": {
                    "code": "search_failed",
                    "message": "搜索服务调用失败",
                    "details": {},
                },
            }

    async def _invoke_search(self, query: str) -> JsonObject:
        args = (
            self._tools,
            query,
            int(getattr(self._settings, "max_search_results_per_query", 5)),
            None,
        )
        async_call = inspect.iscoroutinefunction(self._search) or (
            hasattr(self._search, "__call__")
            and inspect.iscoroutinefunction(self._search.__call__)
        )
        if async_call:
            return await self._search(*args)
        return await asyncio.to_thread(self._search, *args)

    async def _fetch_claimed_urls(self, urls: Sequence[str]) -> dict[str, str]:
        errors: dict[str, str] = {}
        network_urls = [url for url in urls if url not in self._document_cache]
        if self._budget is not None and network_urls:
            allowed = await self._budget.acquire_pages(
                len(network_urls), datetime.now(UTC)
            )
        else:
            allowed = len(network_urls)
        for url in network_urls[allowed:]:
            errors[url] = "page_budget"

        fetched = await asyncio.gather(
            *(self._fetch_one(url) for url in network_urls[:allowed]),
            return_exceptions=True,
        )
        for url, value in zip(network_urls[:allowed], fetched, strict=True):
            if isinstance(value, BaseException):
                errors[url] = self._fetch_error_code(value)
                continue
            self._cache_document(value, requested_alias=url)
        return errors

    async def _fetch_one(self, url: str) -> RawDocument:
        async with self._fetch_semaphore:
            return await self._fetcher.fetch(url)

    def _cache_document(
        self, document: RawDocument, *, requested_alias: str | None = None
    ) -> None:
        aliases = [
            requested_alias,
            document.requested_url,
            document.final_url,
            document.canonical_url,
        ]
        for alias in aliases:
            if not alias:
                continue
            try:
                normalized = normalize_url_before_fetch(alias)
            except ValueError:
                continue
            self._document_cache[normalized] = document

    @staticmethod
    def _document_from_search_result(
        normalized_url: str,
        item: Mapping[str, Any],
        content: str,
    ) -> RawDocument:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        identity = hashlib.sha256(
            f"{normalized_url}\0{content_hash}".encode("utf-8")
        ).hexdigest()[:20]
        title = item.get("title")
        return RawDocument(
            doc_id=f"search-{identity}",
            requested_url=normalized_url,
            final_url=normalized_url,
            canonical_url=normalized_url,
            title=(title.strip() if isinstance(title, str) else "")
            or normalized_url,
            content=content,
            content_hash=content_hash,
            fetched_at=datetime.now(UTC),
            scraper_used=ScraperUsed.SEARCH_PROVIDER,
            status="success",
        )

    @staticmethod
    def _payload_error_code(payload: Mapping[str, Any]) -> str:
        error = payload.get("error", {})
        if isinstance(error, Mapping):
            return str(error.get("code", "search_failed"))
        return "search_failed"

    @staticmethod
    def _fetch_error_code(error: BaseException) -> str:
        if isinstance(error, WebFetchError):
            return error.code
        return "fetch_failed"
