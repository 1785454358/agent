"""Write policy: when and what may enter long-term memory."""

from __future__ import annotations

from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType

_ALLOWED_SOURCES = {"user_request", "consolidation", "repeated_preference"}


class MemoryWritePolicy:
    """Gate every long-term write; one-off or unsupported content is rejected."""

    def can_store(self, record: MemoryRecord, *, source: str) -> bool:
        if source not in _ALLOWED_SOURCES:
            return False
        if not isinstance(record, MemoryRecord) or record.status is not MemoryStatus.ACTIVE:
            return False
        if record.type is MemoryType.FACT:
            # facts require source evidence support
            return bool(record.source_evidence_ids)
        if record.type is MemoryType.PREFERENCE:
            return source in {"user_request", "repeated_preference"}
        if record.type is MemoryType.EVIDENCE:
            return bool(record.source_evidence_ids)
        if record.type is MemoryType.EPISODE:
            return source == "consolidation"
        return False


async def remember(store, record: MemoryRecord, policy: MemoryWritePolicy) -> MemoryRecord:
    """Versioned upsert; identical content is idempotent, changes supersede."""
    existing = await store.get(record.namespace, record.identity())
    if existing is None:
        stored = await store.put(record)
        return stored
    if existing.content == record.content:
        return existing
    if existing.status is not MemoryStatus.ACTIVE:
        # re-activate a new version over a non-active predecessor
        pass
    new_version = MemoryRecord.model_validate(
        {
            **record.model_dump(),
            "id": "",
            "version": existing.version + 1,
            "supersedes": existing.id,
            "created_at": record.created_at,
        }
    )
    superseded = existing.model_copy(
        update={"status": MemoryStatus.SUPERSEDED}, deep=True
    )
    await store.put(superseded)
    stored = await store.put(new_version)
    return stored
