"""Run-owned caches and single-flight external operations."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from deeptrace.multi_agent.runtime import QuotaManager, ToolLease
from deeptrace.tools.scraper import normalize_url_before_fetch

T = TypeVar("T")
_memory_locks: dict[str, asyncio.Lock] = {}
WRITER_SOURCE_CHARS = 3_000


@dataclass(frozen=True)
class CachedValue(Generic[T]):
    value: T
    cached: bool


@dataclass(frozen=True)
class FetchResult:
    document: Any | None
    cached: bool
    error: str | None = None


class SharedResearchResources:
    """Own external dependencies and de-duplicate work across Researchers."""

    def __init__(
        self,
        *,
        search,
        fetcher,
        total_tool_calls: int = 30,
        per_researcher_tool_calls: int = 10,
        quota: QuotaManager | None = None,
        compressor=None,
        embeddings=None,
        memory=None,
        settings=None,
    ) -> None:
        self._search = search
        self.fetcher = fetcher
        self.quota = quota or QuotaManager(
            total=total_tool_calls,
            per_researcher=per_researcher_tool_calls,
        )
        self.compressor = compressor
        self.embeddings = embeddings
        self.memory = memory
        self.settings = settings
        self._search_cache: dict[str, dict] = {}
        self._page_cache: dict[str, Any] = {}
        self.documents: dict[str, Any] = {}
        self.queries: list[str] = []
        self._contexts: dict[str, dict[str, str]] = {}
        self._search_inflight: dict[str, asyncio.Future[dict]] = {}
        self._page_inflight: dict[str, asyncio.Future[FetchResult]] = {}
        self._flight_lock = asyncio.Lock()
        self._context_lock = asyncio.Lock()

    async def _claim_flight(self, flights: dict, key: str):
        async with self._flight_lock:
            future = flights.get(key)
            if future is not None:
                return future, False
            future = asyncio.get_running_loop().create_future()
            flights[key] = future
            return future, True

    async def _release_flight(self, flights: dict, key: str, future) -> None:
        async with self._flight_lock:
            if flights.get(key) is future:
                flights.pop(key, None)

    async def search(self, query: str, lease: ToolLease) -> CachedValue[dict]:
        key = query.strip()
        if key and key not in self.queries:
            self.queries.append(key)
        if key in self._search_cache:
            return CachedValue(self._search_cache[key], True)
        future, leader = await self._claim_flight(self._search_inflight, key)
        if not leader:
            value = await asyncio.shield(future)
            return CachedValue(value, bool(value.get("ok")))
        value: dict = {"ok": False, "error": "search_failed"}
        try:
            if not await lease.acquire_network():
                value = {"ok": False, "error": "tool_call_limit"}
                future.set_result(value)
                return CachedValue(value, False)
            try:
                async_call = inspect.iscoroutinefunction(self._search) or (
                    callable(self._search)
                    and inspect.iscoroutinefunction(self._search.__call__)
                )
                if async_call:
                    value = await self._search(key)
                else:
                    value = await asyncio.to_thread(self._search, key)
                    if inspect.isawaitable(value):
                        value = await value
            except asyncio.CancelledError:
                value = {"ok": False, "error": "cancelled"}
                future.set_result(value)
                raise
            except Exception as exc:  # noqa: BLE001 - sanitize external search errors
                value = {"ok": False, "error": type(exc).__name__}
            if not isinstance(value, dict):
                value = {"ok": False, "error": "invalid_search_response"}
            if value.get("ok"):
                self._search_cache[key] = value
            future.set_result(value)
            return CachedValue(value, False)
        finally:
            if not future.done():
                future.set_result(value)
            await self._release_flight(self._search_inflight, key, future)

    async def fetch(
        self, url: str, lease: ToolLease, *, refresh: bool = False
    ) -> FetchResult:
        try:
            normalized = normalize_url_before_fetch(url)
        except (TypeError, ValueError):
            return FetchResult(None, False, "invalid_url")
        if not refresh and normalized in self._page_cache:
            return FetchResult(self._page_cache[normalized], True)
        flight_key = normalized + ("#refresh" if refresh else "")
        future, leader = await self._claim_flight(self._page_inflight, flight_key)
        if not leader:
            result = await asyncio.shield(future)
            return FetchResult(
                result.document,
                result.error is None,
                result.error,
            )
        result = FetchResult(None, False, "fetch_failed")
        try:
            if not await lease.acquire_network():
                result = FetchResult(None, False, "tool_call_limit")
                future.set_result(result)
                return result
            try:
                document = await self.fetcher.fetch(normalized)
            except asyncio.CancelledError:
                result = FetchResult(None, False, "cancelled")
                future.set_result(result)
                raise
            except Exception as exc:  # noqa: BLE001 - sanitize external fetch errors
                result = FetchResult(None, False, type(exc).__name__)
                future.set_result(result)
                return result
            if getattr(document, "status", None) != "success" or not getattr(
                document, "content", ""
            ).strip():
                result = FetchResult(document, False, "empty_page")
                future.set_result(result)
                return result
            self._page_cache[normalized] = document
            result = FetchResult(document, False)
            future.set_result(result)
            return result
        finally:
            if not future.done():
                future.set_result(result)
            await self._release_flight(self._page_inflight, flight_key, future)

    async def ingest(self, task_id: str, objective: str, document) -> tuple[str, str]:
        source = normalize_url_before_fetch(
            document.final_url or document.requested_url
        )
        async with self._context_lock:
            if self.compressor is None:
                context = document.content
            else:
                context = await self.compressor.aget_context(
                    objective, [document], max_results=5
                )
        if not str(context).strip():
            raise ValueError("no_relevant_content")
        self.documents[source] = document
        self._contexts.setdefault(task_id, {})[source] = str(context)[
            :WRITER_SOURCE_CHARS
        ]
        return source, str(context)

    def context_for(self, task_id: str, source: str) -> str:
        return self._contexts.get(task_id, {}).get(source, "")

    def writer_material(
        self, results: list[Any], *, max_chars: int = 50_000
    ) -> tuple[str, list[str]]:
        ordered: list[tuple[str, str]] = []
        seen: set[str] = set()
        for result in results:
            task_contexts = self._contexts.get(result.task_id, {})
            for source in result.source_urls:
                if source in seen or source not in task_contexts:
                    continue
                seen.add(source)
                ordered.append((source, task_contexts[source]))
        if not ordered:
            return "", []
        while ordered:
            header_chars = sum(len(f"Source: {source}\n") for source, _ in ordered)
            separator_chars = 2 * (len(ordered) - 1)
            if header_chars + separator_chars + len(ordered) <= max_chars:
                break
            ordered.pop()
        if not ordered:
            return "", []
        overhead = sum(len(f"Source: {source}\n") for source, _ in ordered) + 2 * (
            len(ordered) - 1
        )
        text_budget = max_chars - overhead
        base, extra = divmod(text_budget, len(ordered))
        context = "\n\n".join(
            f"Source: {source}\n{text[: base + (1 if index < extra else 0)]}"
            for index, (source, text) in enumerate(ordered)
        )
        return context, [source for source, _ in ordered]

    def cache_memory_document(self, url: str, document: Any) -> None:
        self._page_cache[normalize_url_before_fetch(url)] = document

    async def aclose(self) -> None:
        await self.fetcher.aclose()

    async def persist(self) -> None:
        if self.memory is None or not self.documents:
            return
        memory_path = str(getattr(self.memory, "_path", "multi-agent-memory"))
        async with _memory_locks.setdefault(memory_path, asyncio.Lock()):
            await asyncio.to_thread(
                self.memory.add_documents, list(self.documents.values())
            )
