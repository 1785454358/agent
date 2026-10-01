from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event

from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.evidence_store import SqlAlchemyEvidenceStore
from deeptrace.persistence.orm import Base
from deeptrace.tools.evidence_store import EvidenceDraft


async def _make_store(tmp_path):
    engine, sessions = create_session_factory(
        f"sqlite+aiosqlite:///{tmp_path}/evidence.db"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlAlchemyEvidenceStore(sessions)


def _draft(body: str) -> EvidenceDraft:
    return EvidenceDraft(
        canonical_url="https://example.com/a",
        title="来源 A",
        media_type="text/html",
        body=body,
        fetched_at=datetime(2026, 9, 13, tzinfo=UTC),
        source_quality=0.9,
    )


@pytest_asyncio.fixture
async def instrumented_store(tmp_path):
    engine, sessions = create_session_factory(
        f"sqlite+aiosqlite:///{tmp_path}/batch.db"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    selects = []

    def track_select(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", track_select)
    try:
        yield SqlAlchemyEvidenceStore(sessions), selects
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", track_select)
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_many_batches_metadata_and_preserves_order(instrumented_store):
    store, selects = instrumented_store
    first = await store.ingest("tenant-1", _draft("first"))
    second = await store.ingest("tenant-1", _draft("second"))
    selects.clear()

    records = await store.get_many(
        " tenant-1 ", [second.id, f" {first.id} ", second.id]
    )

    assert [record.id for record in records] == [second.id, first.id, second.id]
    assert len(selects) == 1
    assert "evidence_records.body" not in selects[0]
    assert records[0].status == second.status
    assert records[1].status.value == "superseded"
    records[0].metadata["changed"] = True
    records[0].title = "changed"
    assert records[2].title == second.title
    assert "changed" not in records[2].metadata
    assert await store.read_body("tenant-1", second.id) == "second"


@pytest.mark.asyncio
async def test_get_many_limits_each_query_to_400_unique_ids(instrumented_store):
    store, selects = instrumented_store
    records = [
        await store.ingest(
            "tenant-1",
            _draft(f"body-{index}").model_copy(
                update={"canonical_url": f"https://example.com/{index}"}
            ),
        )
        for index in range(401)
    ]
    selects.clear()
    requested = [record.id for record in records]

    result = await store.get_many("tenant-1", requested)

    assert [record.id for record in result] == requested
    assert len(selects) == 2
    assert all("evidence_records.body" not in sql for sql in selects)


@pytest.mark.asyncio
async def test_get_many_empty_input_does_not_query(instrumented_store):
    store, selects = instrumented_store
    assert await store.get_many("tenant-1", []) == ()
    assert selects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_kind", ["absent", "foreign_tenant"])
async def test_get_many_is_strict_and_tenant_scoped(instrumented_store, missing_kind):
    store, selects = instrumented_store
    local = await store.ingest("tenant-1", _draft("local"))
    foreign = await store.ingest("tenant-2", _draft("foreign"))
    missing = "missing" if missing_kind == "absent" else foreign.id
    with pytest.raises(KeyError, match="evidence is not available for tenant"):
        await store.get_many("tenant-1", [local.id, missing])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tenant", "ids", "error"),
    [
        ("", [], ValueError),
        ("tenant-1", [" "], ValueError),
        ("tenant-1", [None], ValueError),
        ("tenant-1", "one-id", TypeError),
        ("tenant-1", b"one-id", TypeError),
    ],
)
async def test_get_many_validates_before_querying(
    instrumented_store, tenant, ids, error
):
    store, selects = instrumented_store
    with pytest.raises(error):
        await store.get_many(tenant, ids)
    assert selects == []


@pytest.mark.asyncio
async def test_evidence_versions_supersede_and_bodies_persist(tmp_path) -> None:
    store = await _make_store(tmp_path)

    first = await store.ingest("tenant-1", _draft("正文版本一"))
    second = await store.ingest("tenant-1", _draft("正文版本二"))
    duplicate = await store.ingest("tenant-1", _draft("正文版本二"))

    assert first.id != second.id
    assert second.version == 2
    assert second.supersedes == first.id
    assert duplicate.id == second.id
    assert (await store.read_body("tenant-1", second.id)) == "正文版本二"
    assert (await store.read_body("tenant-1", first.id)) == "正文版本一"
    latest = await store.latest_for_source("tenant-1", "https://example.com/a")
    assert latest.id == second.id
    with pytest.raises(KeyError):
        await store.get("other-tenant", second.id)


@pytest.mark.asyncio
async def test_evidence_bodies_survive_a_new_store_instance(tmp_path) -> None:
    store = await _make_store(tmp_path)
    evidence = await store.ingest("tenant-1", _draft("重启后仍可读的正文"))

    reopened = await _make_store(tmp_path)
    body = await reopened.read_body("tenant-1", evidence.id)

    assert body == "重启后仍可读的正文"


@pytest.mark.asyncio
async def test_concurrent_different_bodies_keep_every_version(tmp_path) -> None:
    import asyncio

    store = await _make_store(tmp_path)
    draft_a = EvidenceDraft(
        canonical_url="https://example.com/race",
        title="A",
        media_type="text/html",
        body="并发正文 A",
        fetched_at=datetime(2026, 9, 13, tzinfo=UTC),
        source_quality=0.9,
    )
    draft_b = EvidenceDraft(
        canonical_url="https://example.com/race",
        title="B",
        media_type="text/html",
        body="并发正文 B",
        fetched_at=datetime(2026, 9, 13, tzinfo=UTC),
        source_quality=0.9,
    )

    results = await asyncio.gather(
        store.ingest("tenant-1", draft_a), store.ingest("tenant-1", draft_b)
    )
    bodies = {await store.read_body("tenant-1", item.id) for item in results}
    # neither submitted body may be silently dropped
    assert bodies == {"并发正文 A", "并发正文 B"}
    latest = await store.latest_for_source("tenant-1", "https://example.com/race")
    assert await store.read_body("tenant-1", latest.id) in bodies
