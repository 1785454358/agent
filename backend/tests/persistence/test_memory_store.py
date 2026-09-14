from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.memory_store import SqlAlchemyMemoryStore
from deeptrace.persistence.orm import Base

NOW = datetime(2026, 9, 14, tzinfo=UTC)


def _record(
    subject: str,
    *,
    namespace: tuple[str, str, str] = ("workspace", "ws-1", "facts"),
    memory_type: MemoryType = MemoryType.FACT,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    expires_at: datetime | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        type=memory_type,
        namespace=namespace,
        subject=subject,
        content=f"{subject} 的完整记忆内容",
        source_evidence_ids=["evidence-1"] if memory_type is MemoryType.FACT else [],
        confidence=0.9,
        importance=0.8,
        status=status,
        created_at=NOW,
        updated_at=NOW,
        expires_at=expires_at,
    )


async def _make_store(tmp_path) -> tuple[SqlAlchemyMemoryStore, object]:
    engine, sessions = create_session_factory(
        f"sqlite+aiosqlite:///{tmp_path}/memory.db"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return SqlAlchemyMemoryStore(sessions), engine


@pytest.mark.asyncio
async def test_list_eligible_filters_scope_type_status_and_expiry(tmp_path) -> None:
    store, engine = await _make_store(tmp_path)
    wanted = _record("wanted")
    records = [
        wanted,
        _record("other-scope", namespace=("workspace", "ws-2", "facts")),
        _record(
            "wrong-type",
            memory_type=MemoryType.PREFERENCE,
            namespace=("workspace", "ws-1", "facts"),
        ),
        _record("deleted", status=MemoryStatus.DELETED),
        _record("candidate", status=MemoryStatus.CANDIDATE),
        _record("expired", expires_at=NOW - timedelta(seconds=1)),
    ]
    for record in records:
        await store.put(record)

    found = await store.list_eligible(
        namespaces=[("workspace", "ws-1", "facts")],
        memory_types={MemoryType.FACT},
        now=NOW,
    )

    assert [record.id for record in found] == [wanted.id]
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_many_by_ids_returns_authoritative_records_in_requested_order(
    tmp_path,
) -> None:
    store, engine = await _make_store(tmp_path)
    first = _record("first")
    second = _record("second")
    await store.put(first)
    await store.put(second)

    found = await store.get_many_by_ids([second.id, "missing", first.id])

    assert [record.id for record in found] == [second.id, first.id]
    assert found[0].content == "second 的完整记忆内容"
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_many_by_ids_prefers_active_latest_legacy_duplicate(tmp_path) -> None:
    store, engine = await _make_store(tmp_path)
    first = _record("versioned").model_copy(
        update={"id": "legacy-shared-id", "status": MemoryStatus.SUPERSEDED}
    )
    latest = _record("versioned").model_copy(
        update={
            "id": "legacy-shared-id",
            "content": "latest authoritative content",
            "version": 2,
        }
    )
    await store.put(latest)
    await store.put(first)

    found = await store.get_many_by_ids(["legacy-shared-id"])

    assert len(found) == 1
    assert found[0].version == 2
    assert found[0].content == "latest authoritative content"
    await engine.dispose()
