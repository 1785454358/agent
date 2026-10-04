"""Version updates must remain consistent across both authoritative stores."""

import asyncio
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from deeptrace.application.assembly import _build_durable_stores
from deeptrace.config import Settings
from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType
from deeptrace.harness.memory.forget import forget
from deeptrace.harness.memory.store import InMemoryMemoryStore
from deeptrace.harness.memory.write import MemoryWritePolicy, remember

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def preference(content="请用中文"):
    return MemoryRecord(
        type=MemoryType.PREFERENCE,
        namespace=("user", "u1", "preferences"),
        subject="language",
        content=content,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest_asyncio.fixture(params=["memory", "sqlite"])
async def store(request, tmp_path):
    if request.param == "memory":
        yield InMemoryMemoryStore()
        return
    settings = Settings(
        openai_api_key="test",
        openai_base_url="http://127.0.0.1:1",
        openai_model="test",
        tavily_api_key="test",
    )
    _, _, memory, _, engine = _build_durable_stores(settings, tmp_path)
    try:
        yield memory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_remember_enforces_admission_at_the_write_boundary():
    record = preference().model_copy(update={"type": MemoryType.FACT})
    with pytest.raises(ValueError, match="memory_write_rejected"):
        await remember(InMemoryMemoryStore(), record, MemoryWritePolicy())


@pytest.mark.asyncio
async def test_explicit_write_reactivates_same_content_as_a_new_version():
    memory = InMemoryMemoryStore()
    first = await memory.put(preference())
    await forget(memory, first)
    restored = await remember(
        memory, preference(), MemoryWritePolicy(), source="user_request"
    )
    assert restored.status is MemoryStatus.ACTIVE
    assert restored.version == 2 and restored.supersedes == first.id


@pytest.mark.asyncio
async def test_concurrent_updates_keep_one_current_version(store):
    first = await store.put(preference())
    await asyncio.gather(*(store.upsert(preference(f"language-{i}")) for i in range(5)))
    history = await store.list_namespace(first.namespace, include_inactive=True)
    assert len(history) == 6
    assert sorted(r.version for r in history) == [1, 2, 3, 4, 5, 6]
    assert sum(r.status is MemoryStatus.ACTIVE for r in history) == 1
    by_version = {r.version: r for r in history}
    assert all(by_version[i].supersedes == by_version[i - 1].id for i in range(2, 7))


@pytest.mark.asyncio
async def test_logical_forget_removes_all_visible_versions(store):
    old = await store.put(preference())
    # Characterize legacy data where two versions were left ACTIVE.
    latest = preference("请用英文").model_copy(
        update={"id": "new-version", "version": 2}
    )
    await store.put(latest)
    await forget(store, latest)
    eligible = await store.list_eligible(
        namespaces=[old.namespace],
        memory_types={MemoryType.PREFERENCE},
        now=NOW,
    )
    assert eligible == []
    history = await store.list_namespace(old.namespace, include_inactive=True)
    assert all(r.status is MemoryStatus.DELETED for r in history)


@pytest.mark.asyncio
@pytest.mark.parametrize("store", ["sqlite"], indirect=True)
async def test_sqlite_update_failure_rolls_back_superseding(store, monkeypatch):
    first = await store.put(preference())
    save = store._save

    async def fail_on_new_version(session, record, **kwargs):
        if record.version == 2:
            raise RuntimeError("interrupted before new version")
        await save(session, record, **kwargs)

    monkeypatch.setattr(store, "_save", fail_on_new_version)
    with pytest.raises(RuntimeError, match="interrupted"):
        await store.upsert(preference("请用英文"))
    current = await store.get(first.namespace, first.identity())
    assert current.id == first.id and current.status is MemoryStatus.ACTIVE
    assert len(await store.list_namespace(first.namespace, include_inactive=True)) == 1


@pytest.mark.asyncio
async def test_deleted_fact_is_not_resurrected_by_consolidation_replay(store):
    fact = preference("checkpoint saves state").model_copy(
        update={
            "type": MemoryType.FACT,
            "source_evidence_ids": ["evidence-1"],
        }
    )
    stored = await remember(store, fact, MemoryWritePolicy(), supported_fact=True)
    await forget(store, stored)
    replay = await remember(store, fact, MemoryWritePolicy(), supported_fact=True)
    assert replay.status is MemoryStatus.DELETED
    assert len(await store.list_namespace(fact.namespace, include_inactive=True)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [MemoryStatus.DELETED, MemoryStatus.EXPIRED])
async def test_latest_inactive_version_blocks_legacy_active_version(store, status):
    old = await store.put(preference())
    latest = MemoryRecord.model_validate(
        {
            **preference("请用英文").model_dump(),
            "id": "",
            "version": 2,
            "status": status,
        }
    )
    await store.put(latest)
    assert (await store.get(old.namespace, old.identity())).id == latest.id
    assert (
        await store.list_eligible(
            namespaces=[old.namespace],
            memory_types={MemoryType.PREFERENCE},
            now=NOW,
        )
        == []
    )


@pytest.mark.asyncio
async def test_identity_operations_do_not_match_a_subject_prefix(store):
    first = await store.put(preference())
    other = MemoryRecord.model_validate(
        {
            **preference("unrelated preference").model_dump(),
            "id": "",
            "subject": "language|v-shadow",
            "version": 7,
        }
    )
    await store.put(other)
    assert (await store.get(first.namespace, first.identity())).id == first.id
    updated = await store.upsert(preference("请用英文"))
    assert updated.version == 2
    await forget(store, updated)
    assert (
        await store.get(other.namespace, other.identity())
    ).status is MemoryStatus.ACTIVE
    await store.delete(first.namespace, first.identity())
    assert (await store.get(other.namespace, other.identity())).id == other.id
