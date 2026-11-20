from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.domain import ToolName
from deeptrace.models import RawDocument
from deeptrace.tools.contracts import (
    CachePolicy,
    ToolAdapterResult,
    ToolCallContext,
    ToolCapability,
    ToolSpec,
)
from deeptrace.tools.evidence_read import ReadEvidenceAdapter, ReadEvidenceArguments
from deeptrace.tools.evidence_store import EvidenceDraft, EvidenceStore
from deeptrace.tools.registry import ToolRegistry
from deeptrace.tools.scraper import WebFetchError, normalize_url_before_fetch


class SearchWebArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1_000)
    limit: int = Field(default=5, ge=1, le=8)
    search_depth: Literal["basic", "advanced"] = "basic"
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def valid_window(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("invalid_search_window")
        return self


class FetchPageArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2_048)
    page_start: int | None = Field(default=None, strict=True, ge=1)
    page_end: int | None = Field(default=None, strict=True, ge=1)

    @model_validator(mode="after")
    def valid_pdf_range(self):
        if ((self.page_start is None) != (self.page_end is None)
                or self.page_start is not None and (self.page_end < self.page_start
                    or self.page_end - self.page_start >= 100)):
            raise ValueError("invalid_pdf_page_range")
        return self


class SearchMemoryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1_000)
    limit: int = Field(default=3, ge=1, le=10)


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> RawDocument: ...


class PageMemory(Protocol):
    def entries(self) -> list[Any]: ...


SearchCallable = Callable[..., Any]
ClockCallable = Callable[[], datetime]


class _ResearchToolAdapters:
    def __init__(
        self,
        *,
        search: SearchCallable,
        fetcher: PageFetcher,
        memory: PageMemory | None,
        memory_max_age_days: int,
        now: ClockCallable,
    ) -> None:
        self._search = search
        self._fetcher = fetcher
        self._memory = memory
        self._memory_max_age_days = memory_max_age_days
        self._now = now

    async def search_web(
        self, arguments: BaseModel, _context: ToolCallContext
    ) -> ToolAdapterResult:
        if not isinstance(arguments, SearchWebArguments):
            raise TypeError("search arguments have the wrong type")
        query = arguments.query.strip()
        options = {"max_results": arguments.limit}
        if arguments.search_depth != "basic":
            options["search_depth"] = arguments.search_depth
        for key in ("start_date", "end_date"):
            value = getattr(arguments, key)
            if value:
                options[key] = value.isoformat()
        try:
            response = await _call_search(self._search, query, **options)
        except ValueError as exc:
            if str(exc) == "unsupported_search_options":
                return ToolAdapterResult.failure("unsupported_search_options")
            raise
        if not isinstance(response, dict) or not response.get("ok"):
            error = response.get("error") if isinstance(response, dict) else None
            code = "search_failed"
            message: str | None = None
            if isinstance(error, dict):
                if isinstance(error.get("code"), str) and error["code"].strip():
                    code = error["code"].strip()
                if isinstance(error.get("message"), str):
                    message = error["message"]
            return ToolAdapterResult.failure(code, message=message)

        results: list[dict[str, Any]] = []
        for item in response.get("results", []):
            if not isinstance(item, dict):
                continue
            try:
                url = normalize_url_before_fetch(str(item.get("url", "")))
            except (TypeError, ValueError):
                continue
            results.append(
                {
                    "url": url,
                    "title": str(item.get("title", ""))[:300],
                    "snippet": str(item.get("snippet", item.get("content", "")))[:500],
                }
            )
            if isinstance(item.get("discovery_date"), str):
                results[-1]["discovery_date"] = item["discovery_date"][:128]
            if len(results) >= arguments.limit:
                break
        return ToolAdapterResult(preview=_search_preview(results))

    async def fetch_page(
        self, arguments: BaseModel, _context: ToolCallContext
    ) -> ToolAdapterResult:
        if not isinstance(arguments, FetchPageArguments):
            raise TypeError("fetch arguments have the wrong type")
        try:
            options = ({"page_start": arguments.page_start, "page_end": arguments.page_end}
                       if arguments.page_start is not None else {})
            document = await self._fetcher.fetch(arguments.url, **options)
        except WebFetchError as exc:
            return ToolAdapterResult.failure(exc.code, message=str(exc))
        if document.status != "success" or not document.content.strip():
            return ToolAdapterResult.failure("empty_page")
        # Publisher canonical links may merge different editions/languages.
        # The store versions the actual retrieved resource, not that SEO hint.
        source_url = document.final_url or document.requested_url
        draft = EvidenceDraft(
            canonical_url=source_url,
            title=document.title.strip() or source_url,
            media_type=document.media_type,
            body=document.full_content or document.content,
            fetched_at=document.fetched_at,
            published_at=document.source_published_at,
            source_quality=_source_quality(document),
            metadata={
                "requested_url": document.requested_url,
                "final_url": document.final_url,
                "publisher_canonical_url": document.canonical_url,
                "scraper_used": document.scraper_used.value,
                "publisher": document.publisher,
            },
        )
        return ToolAdapterResult(
            preview=_json_preview(
                {
                    "url": source_url,
                    "title": draft.title,
                    "fetched_at": draft.fetched_at.isoformat(),
                    "published_at": (
                        None
                        if draft.published_at is None
                        else draft.published_at.isoformat()
                    ),
                }
            ),
            evidence=draft,
        )

    async def search_memory(
        self, arguments: BaseModel, _context: ToolCallContext
    ) -> ToolAdapterResult:
        if not isinstance(arguments, SearchMemoryArguments):
            raise TypeError("memory arguments have the wrong type")
        if self._memory is None:
            return ToolAdapterResult.failure("memory_disabled")
        entries = await asyncio.to_thread(self._memory.entries)
        cutoff = _as_utc(self._now()) - timedelta(days=self._memory_max_age_days)
        tokens = _tokens(arguments.query)
        recent = [entry for entry in entries if _as_utc(entry.fetched_at) >= cutoff]
        ranked = sorted(
            recent,
            key=lambda entry: (
                len(tokens & _tokens(str(entry.title))),
                _as_utc(entry.fetched_at),
            ),
            reverse=True,
        )[: arguments.limit]
        results = []
        for entry in ranked:
            try:
                url = normalize_url_before_fetch(entry.url)
            except (TypeError, ValueError):
                continue
            results.append(
                {
                    "url": url,
                    "title": str(entry.title)[:300],
                    "fetched_at": _as_utc(entry.fetched_at).isoformat(),
                    "notice": "historical_source_requires_freshness_check",
                }
            )
        return ToolAdapterResult(preview=_json_preview({"results": results}))


def build_research_tool_registry(
    *,
    search: SearchCallable,
    fetcher: PageFetcher,
    memory: PageMemory | None = None,
    memory_max_age_days: int = 7,
    now: ClockCallable | None = None,
    evidence_store: EvidenceStore | None = None,
) -> ToolRegistry:
    if not callable(search):
        raise TypeError("search must be callable")
    if not callable(getattr(fetcher, "fetch", None)):
        raise TypeError("fetcher must provide fetch")
    if memory is not None and not callable(getattr(memory, "entries", None)):
        raise TypeError("memory must provide entries")
    if (
        not isinstance(memory_max_age_days, int)
        or isinstance(memory_max_age_days, bool)
        or memory_max_age_days <= 0
    ):
        raise ValueError("memory_max_age_days must be a positive int")
    clock = now or (lambda: datetime.now(UTC))
    adapters = _ResearchToolAdapters(
        search=search,
        fetcher=fetcher,
        memory=memory,
        memory_max_age_days=memory_max_age_days,
        now=clock,
    )
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name=ToolName.SEARCH_WEB,
            argument_model=SearchWebArguments,
            handler=adapters.search_web,
            capability=ToolCapability.WEB_SEARCH,
            cache_policy=CachePolicy.SUCCESS,
            timeout_seconds=20.0,
            preview_limit=4_000,
            stores_evidence=False,
        )
    )
    registry.register(
        ToolSpec(
            name=ToolName.FETCH_PAGE,
            argument_model=FetchPageArguments,
            handler=adapters.fetch_page,
            capability=ToolCapability.PAGE_FETCH,
            cache_policy=CachePolicy.SUCCESS,
            timeout_seconds=30.0,
            preview_limit=1_000,
            stores_evidence=True,
        )
    )
    registry.register(
        ToolSpec(
            name=ToolName.SEARCH_MEMORY,
            argument_model=SearchMemoryArguments,
            handler=adapters.search_memory,
            capability=ToolCapability.MEMORY_READ,
            cache_policy=CachePolicy.NONE,
            timeout_seconds=5.0,
            preview_limit=2_000,
            stores_evidence=False,
        )
    )
    if evidence_store is not None:
        reader = ReadEvidenceAdapter(evidence_store)
        registry.register(
            ToolSpec(
                name=ToolName.READ_EVIDENCE,
                argument_model=ReadEvidenceArguments,
                handler=reader.read,
                preflight=reader.preflight,
                capability=ToolCapability.EVIDENCE_READ,
                cache_policy=CachePolicy.NONE,
                timeout_seconds=5.0,
                preview_limit=4000,
                stores_evidence=False,
            )
        )
    return registry


async def _call_search(search: SearchCallable, query: str, **options) -> Any:
    parameters = inspect.signature(search).parameters
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        # Query-only injected providers remain valid for basic search. A
        # requested time/depth policy must never silently disappear.
        if set(options) - set(parameters) - {"max_results"}:
            raise ValueError("unsupported_search_options")
        options = {key: value for key, value in options.items() if key in parameters}
    async_call = inspect.iscoroutinefunction(search) or inspect.iscoroutinefunction(
        getattr(search, "__call__", None)  # noqa: B004 - async callable instances
    )
    response = (
        await search(query, **options)
        if async_call
        else await asyncio.to_thread(search, query, **options)
    )
    if inspect.isawaitable(response):
        return await response
    return response


def _json_preview(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _search_preview(results: list[dict[str, Any]], limit: int = 4000) -> str:
    """Fit complete records/JSON before the gateway's generic string clamp."""
    payload = {"results": results}
    for field, floor in (("snippet", 120), ("title", 80)):
        while len(_json_preview(payload)) > limit and any(
            len(row[field]) > floor for row in results
        ):
            for row in results:
                row[field] = row[field][: max(floor, len(row[field]) // 2)]
    omitted = 0
    while results and len(_json_preview(payload)) > limit:
        results.pop()
        omitted += 1
        payload["omitted_results"] = omitted
    return _json_preview(payload)


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"\w+", value)}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC)


def _source_quality(document: RawDocument) -> float:
    return 0.9 if document.canonical_url else 0.8
