from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from deeptrace.domain import ToolResult
from deeptrace.tools.scraper.urls import normalize_url_before_fetch


class SingleflightExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolCacheKey:
    namespace: str
    digest: str

    def __post_init__(self) -> None:
        if not self.namespace or not self.digest:
            raise ValueError("cache key fields must be non-empty")


class SuccessCache(Protocol):
    async def get(self, key: ToolCacheKey) -> ToolResult | None: ...

    async def put(self, key: ToolCacheKey, result: ToolResult) -> bool: ...


class InMemorySuccessCache:
    def __init__(self) -> None:
        self._items: dict[ToolCacheKey, ToolResult] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: ToolCacheKey) -> ToolResult | None:
        _require_key(key)
        async with self._lock:
            result = self._items.get(key)
            return None if result is None else result.model_copy(deep=True)

    async def put(self, key: ToolCacheKey, result: ToolResult) -> bool:
        _require_key(key)
        if not isinstance(result, ToolResult):
            raise TypeError("result must be a ToolResult")
        if not result.ok:
            return False
        stored = result.model_copy(update={"cached": False}, deep=True)
        async with self._lock:
            self._items[key] = stored
        return True


@dataclass(frozen=True)
class _FlightFailure:
    code: str


_FlightOutcome = ToolResult | _FlightFailure
ToolResultFactory = Callable[[], Awaitable[ToolResult]]


class ToolExecutionCoordinator(Protocol):
    async def get_or_execute(
        self,
        key: ToolCacheKey,
        factory: ToolResultFactory,
        *,
        refresh: bool = False,
    ) -> ToolResult: ...


class SuccessCacheSingleflight:
    def __init__(self, cache: SuccessCache) -> None:
        if not isinstance(cache, InMemorySuccessCache) and not (
            callable(getattr(cache, "get", None))
            and callable(getattr(cache, "put", None))
        ):
            raise TypeError("cache must implement SuccessCache")
        self._cache = cache
        self._flights: dict[ToolCacheKey, asyncio.Future[_FlightOutcome]] = {}
        self._lock = asyncio.Lock()

    async def get_or_execute(
        self,
        key: ToolCacheKey,
        factory: ToolResultFactory,
        *,
        refresh: bool = False,
    ) -> ToolResult:
        _require_key(key)
        if not callable(factory):
            raise TypeError("factory must be callable")
        if not isinstance(refresh, bool):
            raise TypeError("refresh must be a bool")

        if not refresh:
            cached = await self._cache.get(key)
            if cached is not None:
                return cached.model_copy(update={"cached": True}, deep=True)

        async with self._lock:
            if not refresh:
                cached = await self._cache.get(key)
                if cached is not None:
                    return cached.model_copy(update={"cached": True}, deep=True)
            flight = self._flights.get(key)
            if flight is None:
                flight = asyncio.get_running_loop().create_future()
                self._flights[key] = flight
                leader = True
            else:
                leader = False

        if not leader:
            outcome = await asyncio.shield(flight)
            if isinstance(outcome, _FlightFailure):
                raise SingleflightExecutionError("shared execution failed")
            return outcome.model_copy(update={"cached": True}, deep=True)

        try:
            result = await factory()
            if not isinstance(result, ToolResult):
                raise TypeError("factory must return a ToolResult")
        except asyncio.CancelledError:
            await self._finish_failure(key, flight, "leader_cancelled")
            raise
        except Exception:
            await self._finish_failure(key, flight, "leader_failed")
            raise

        leader_result = result.model_copy(update={"cached": False}, deep=True)
        if leader_result.ok:
            await self._cache.put(key, leader_result)
        await self._finish_success(key, flight, leader_result)
        return leader_result

    async def _finish_success(
        self,
        key: ToolCacheKey,
        flight: asyncio.Future[_FlightOutcome],
        result: ToolResult,
    ) -> None:
        async with self._lock:
            if not flight.done():
                flight.set_result(result.model_copy(deep=True))
            if self._flights.get(key) is flight:
                del self._flights[key]

    async def _finish_failure(
        self,
        key: ToolCacheKey,
        flight: asyncio.Future[_FlightOutcome],
        code: str,
    ) -> None:
        async with self._lock:
            if not flight.done():
                flight.set_result(_FlightFailure(code))
            if self._flights.get(key) is flight:
                del self._flights[key]


def search_cache_key(
    query: str,
    provider: str,
    options: Mapping[str, Any],
) -> ToolCacheKey:
    normalized_query = " ".join(_require_text("query", query).split()).casefold()
    normalized_provider = _require_text("provider", provider).casefold()
    return _cache_key(
        "search",
        {
            "query": normalized_query,
            "provider": normalized_provider,
            "options": dict(options),
        },
    )


def page_cache_key(
    url: str,
    *,
    content_version: str | None = None,
) -> ToolCacheKey:
    normalized_url = normalize_url_before_fetch(_require_text("url", url))
    normalized_version = (
        None
        if content_version is None
        else _require_text("content_version", content_version)
    )
    return _cache_key(
        "page",
        {"url": normalized_url, "content_version": normalized_version},
    )


def _cache_key(namespace: str, payload: Mapping[str, Any]) -> ToolCacheKey:
    try:
        serialized = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("cache key payload must be JSON-compatible") from exc
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return ToolCacheKey(namespace=namespace, digest=digest)


def _require_key(key: object) -> None:
    if not isinstance(key, ToolCacheKey):
        raise TypeError("key must be a ToolCacheKey")


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
