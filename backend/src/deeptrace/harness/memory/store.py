"""Memory Store adapter over the LangGraph Store contract."""

from __future__ import annotations

import asyncio

from langgraph.store.memory import InMemoryStore

from deeptrace.domain import MemoryRecord, MemoryStatus
from deeptrace.domain.memory import MemoryNamespace


def namespace_for(scope: str, owner: str, kind: str) -> MemoryNamespace:
    if scope not in {"user", "workspace", "thread", "global"}:
        raise ValueError(f"unknown memory scope: {scope}")
    if not owner.strip() or not kind.strip():
        raise ValueError("memory namespace owner/kind must be non-empty")
    return (scope, owner, kind)


class InMemoryMemoryStore:
    """Typed, namespace-scoped view over a LangGraph-compatible store.

    Every version is kept under its own key so superseded records remain
    queryable for the audit trail.
    """

    def __init__(self, inner: InMemoryStore | None = None) -> None:
        self._inner = inner or InMemoryStore()
        self._lock = asyncio.Lock()

    async def put(self, record: MemoryRecord) -> MemoryRecord:
        if not isinstance(record, MemoryRecord):
            raise TypeError("record must be a MemoryRecord")
        async with self._lock:
            self._inner.put(
                record.namespace, record.store_key(), record.model_dump(mode="json")
            )
            return record.model_copy(deep=True)

    async def get(
        self, namespace: MemoryNamespace, identity: str
    ) -> MemoryRecord | None:
        versions = await self._versions(namespace, identity)
        if not versions:
            return None
        active = [record for record in versions if record.status is MemoryStatus.ACTIVE]
        pool = active or versions
        return max(pool, key=lambda record: record.version).model_copy(deep=True)

    async def list_namespace(
        self, namespace: MemoryNamespace, *, include_inactive: bool = False
    ) -> list[MemoryRecord]:
        async with self._lock:
            items = self._inner.search(namespace)
        records = [MemoryRecord.model_validate(item.value) for item in items]
        if include_inactive:
            return sorted(records, key=lambda record: record.store_key())
        return sorted(
            (
                record
                for record in records
                if record.status
                in {MemoryStatus.ACTIVE, MemoryStatus.STALE, MemoryStatus.CANDIDATE}
            ),
            key=lambda record: record.store_key(),
        )

    async def delete(self, namespace: MemoryNamespace, identity: str) -> bool:
        async with self._lock:
            items = self._inner.search(namespace)
            targets = [
                item
                for item in items
                if item.key.startswith(f"{identity}|v") or item.key == identity
            ]
            for item in targets:
                self._inner.delete(namespace, item.key)
        return bool(targets)

    async def _versions(
        self, namespace: MemoryNamespace, identity: str
    ) -> list[MemoryRecord]:
        async with self._lock:
            items = self._inner.search(namespace)
        return sorted(
            (
                MemoryRecord.model_validate(item.value)
                for item in items
                if item.key.startswith(f"{identity}|v")
            ),
            key=lambda record: record.version,
        )
