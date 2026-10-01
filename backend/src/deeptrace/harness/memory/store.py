"""Memory Store adapter over the LangGraph Store contract."""

from __future__ import annotations

import asyncio
from datetime import datetime

from langgraph.store.base import SearchItem
from langgraph.store.memory import InMemoryStore

from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType
from deeptrace.domain.memory import (
    MemoryNamespace,
    current_memories,
    next_memory_version,
)


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

    def _items(self, namespace: tuple[str, ...]) -> list[SearchItem]:
        """Read all pages under the caller's lock, including version histories."""
        items: list[SearchItem] = []
        while True:
            page = self._inner.search(namespace, limit=100, offset=len(items))
            items.extend(page)
            if len(page) < 100:
                return items

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
        return max(versions, key=lambda record: record.version).model_copy(deep=True)

    async def upsert(
        self,
        record: MemoryRecord,
        *,
        allow_reactivate: bool = True,
    ) -> MemoryRecord:
        async with self._lock:
            versions = [
                MemoryRecord.model_validate(item.value)
                for item in self._items(record.namespace)
                if item.key.rsplit("|v", 1)[0] == record.identity()
            ]
            previous = max(versions, key=lambda r: r.version, default=None)
            stored = next_memory_version(
                record, previous, allow_reactivate=allow_reactivate
            )
            if previous is not None and stored.id == previous.id:
                return stored
            for old in versions:
                if old.status is MemoryStatus.ACTIVE:
                    superseded = old.model_copy(
                        update={"status": MemoryStatus.SUPERSEDED}
                    )
                    self._inner.put(
                        old.namespace,
                        old.store_key(),
                        superseded.model_dump(mode="json"),
                    )
            self._inner.put(
                stored.namespace, stored.store_key(), stored.model_dump(mode="json")
            )
            return stored.model_copy(deep=True)

    async def set_status(
        self,
        namespace: MemoryNamespace,
        identity: str,
        status: MemoryStatus,
    ) -> None:
        async with self._lock:
            for item in self._items(namespace):
                if item.key.rsplit("|v", 1)[0] == identity:
                    record = MemoryRecord.model_validate(item.value)
                    record.status = status
                    self._inner.put(namespace, item.key, record.model_dump(mode="json"))

    async def list_namespace(
        self, namespace: MemoryNamespace, *, include_inactive: bool = False
    ) -> list[MemoryRecord]:
        async with self._lock:
            items = self._items(namespace)
        records = [MemoryRecord.model_validate(item.value) for item in items]
        if include_inactive:
            return sorted(records, key=lambda record: record.store_key())
        return sorted(
            (
                record
                for record in current_memories(records)
                if record.status
                in {MemoryStatus.ACTIVE, MemoryStatus.STALE, MemoryStatus.CANDIDATE}
            ),
            key=lambda record: record.store_key(),
        )

    async def delete(self, namespace: MemoryNamespace, identity: str) -> bool:
        async with self._lock:
            items = self._items(namespace)
            targets = [
                item
                for item in items
                if item.key.rsplit("|v", 1)[0] == identity or item.key == identity
            ]
            for item in targets:
                self._inner.delete(namespace, item.key)
        return bool(targets)

    async def list_eligible(
        self,
        *,
        namespaces: list[MemoryNamespace],
        memory_types: set[MemoryType],
        now: datetime,
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for namespace in namespaces:
            records.extend(await self.list_namespace(namespace))
        return sorted(
            (
                record
                for record in records
                if record.type in memory_types
                and record.status is MemoryStatus.ACTIVE
                and (record.expires_at is None or record.expires_at > now)
            ),
            key=lambda record: record.store_key(),
        )

    async def get_many_by_ids(self, memory_ids: list[str]) -> list[MemoryRecord]:
        wanted = set(memory_ids)
        async with self._lock:
            items = self._items(())
        records = {
            record.id: record
            for item in items
            if (record := MemoryRecord.model_validate(item.value)).id in wanted
        }
        return [records[memory_id] for memory_id in memory_ids if memory_id in records]

    async def _versions(
        self, namespace: MemoryNamespace, identity: str
    ) -> list[MemoryRecord]:
        async with self._lock:
            items = self._items(namespace)
        return sorted(
            (
                MemoryRecord.model_validate(item.value)
                for item in items
                if item.key.rsplit("|v", 1)[0] == identity
            ),
            key=lambda record: record.version,
        )
