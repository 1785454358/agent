"""Forgetting policy: retrieval downgrade, logical and physical deletion."""

from __future__ import annotations

from datetime import datetime

from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType
from deeptrace.domain.memory import STALE_AFTER_DAYS
from deeptrace.harness.memory.recall import is_stale


def apply_lifecycle(
    records: list[MemoryRecord], *, now: datetime
) -> dict[str, MemoryStatus | None]:
    """Return the target status transition per record; None means no change."""
    transitions: dict[str, MemoryStatus | None] = {}
    for record in records:
        target: MemoryStatus | None = None
        if record.status is MemoryStatus.ACTIVE:
            if record.expires_at is not None and record.expires_at <= now:
                target = MemoryStatus.EXPIRED
            elif record.type is not MemoryType.PREFERENCE and is_stale(
                record, now=now
            ):
                target = MemoryStatus.STALE
        transitions[record.id or record.identity()] = target
    return transitions


async def forget(store, record: MemoryRecord, *, mode: str = "logical") -> MemoryRecord:
    if mode not in {"logical", "physical"}:
        raise ValueError("forget mode must be logical or physical")
    if mode == "physical":
        await store.delete(record.namespace, record.identity())
        return record.model_copy(update={"status": MemoryStatus.DELETED}, deep=True)
    deleted = record.model_copy(update={"status": MemoryStatus.DELETED}, deep=True)
    await store.put(deleted)
    return deleted
