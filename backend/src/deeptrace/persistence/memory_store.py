"""SQL-backed long-term memory store over the memory_records table."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType
from deeptrace.domain.memory import (
    MemoryNamespace,
    current_memories,
    next_memory_version,
)
from deeptrace.persistence.orm import MemoryRecordRow


class SqlAlchemyMemoryStore:
    """Same semantics as InMemoryMemoryStore, persisted across restarts.

    One row per record version; ``get`` returns the latest version for
    the identity, superseded versions stay queryable for the audit trail.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._lock = asyncio.Lock()

    async def put(self, record: MemoryRecord) -> MemoryRecord:
        if not isinstance(record, MemoryRecord):
            raise TypeError("record must be a MemoryRecord")
        async with self._lock, self._sessions() as session, session.begin():
            await self._save(session, record)
        return record.model_copy(deep=True)

    @staticmethod
    def _namespace(namespace: MemoryNamespace):
        scope, owner, kind = namespace
        return (
            MemoryRecordRow.namespace_scope == scope,
            MemoryRecordRow.namespace_owner == owner,
            MemoryRecordRow.namespace_kind == kind,
        )

    async def _save(
        self, session: AsyncSession, record: MemoryRecord, *, insert: bool = False
    ) -> None:
        scope, owner, kind = record.namespace
        row = (
            None
            if insert
            else (
                await session.execute(
                    select(MemoryRecordRow).where(
                        *self._namespace(record.namespace),
                        MemoryRecordRow.store_key == record.store_key(),
                    )
                )
            ).scalar_one_or_none()
        )
        if row is None:
            row = MemoryRecordRow(
                namespace_scope=scope,
                namespace_owner=owner,
                namespace_kind=kind,
                store_key=record.store_key(),
            )
            session.add(row)
        row.memory_id = record.id
        row.memory_type = record.type.value
        row.status = record.status.value
        row.importance = record.importance
        row.confidence = record.confidence
        row.created_at = record.created_at
        row.expires_at = record.expires_at
        row.payload = record.model_dump(mode="json")
        row.updated_at = datetime.now(UTC)

    async def upsert(
        self,
        record: MemoryRecord,
        *,
        allow_reactivate: bool = True,
    ) -> MemoryRecord:
        async with self._lock:
            for attempt in range(3):
                try:
                    async with self._sessions() as session, session.begin():
                        rows = (
                            (
                                await session.execute(
                                    select(MemoryRecordRow)
                                    .where(
                                        *self._namespace(record.namespace),
                                        MemoryRecordRow.store_key.startswith(
                                            f"{record.identity()}|v", autoescape=True
                                        ),
                                    )
                                    .with_for_update()
                                )
                            )
                            .scalars()
                            .all()
                        )
                        versions = [
                            MemoryRecord.model_validate(row.payload)
                            for row in rows
                            if row.store_key.rsplit("|v", 1)[0] == record.identity()
                        ]
                        previous = max(versions, key=lambda r: r.version, default=None)
                        stored = next_memory_version(
                            record, previous, allow_reactivate=allow_reactivate
                        )
                        if previous is not None and stored.id == previous.id:
                            return stored
                        for old in versions:
                            if old.status is MemoryStatus.ACTIVE:
                                await self._save(
                                    session,
                                    old.model_copy(
                                        update={"status": MemoryStatus.SUPERSEDED}
                                    ),
                                )
                        await self._save(session, stored, insert=True)
                    return stored.model_copy(deep=True)
                except IntegrityError:
                    # Two processes may concurrently create the first version.
                    # A new transaction observes the winning insert.
                    if attempt == 2:
                        raise
        raise RuntimeError("memory_upsert_exhausted")

    async def set_status(
        self, namespace: MemoryNamespace, identity: str, status: MemoryStatus
    ) -> None:
        async with self._lock, self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(MemoryRecordRow)
                        .where(
                            *self._namespace(namespace),
                            MemoryRecordRow.store_key.startswith(
                                f"{identity}|v", autoescape=True
                            ),
                        )
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                if row.store_key.rsplit("|v", 1)[0] != identity:
                    continue
                record = MemoryRecord.model_validate(row.payload)
                await self._save(session, record.model_copy(update={"status": status}))

    async def get(self, namespace, identity: str) -> MemoryRecord | None:
        versions = await self._versions(namespace, identity)
        if not versions:
            return None
        return max(versions, key=lambda record: record.version).model_copy(deep=True)

    async def list_namespace(
        self, namespace, *, include_inactive: bool = False
    ) -> list[MemoryRecord]:
        scope, owner, kind = namespace
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(MemoryRecordRow).where(
                            MemoryRecordRow.namespace_scope == scope,
                            MemoryRecordRow.namespace_owner == owner,
                            MemoryRecordRow.namespace_kind == kind,
                        )
                    )
                )
                .scalars()
                .all()
            )
        records = [MemoryRecord.model_validate(row.payload) for row in rows]
        if include_inactive:
            return sorted(records, key=lambda record: record.store_key())
        return sorted(
            (
                record
                for record in current_memories(records)
                if record.status.value in {"active", "stale", "candidate"}
            ),
            key=lambda record: record.store_key(),
        )

    async def delete(self, namespace, identity: str) -> bool:
        async with self._lock, self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(MemoryRecordRow)
                        .where(
                            *self._namespace(namespace),
                            MemoryRecordRow.store_key.startswith(
                                f"{identity}|v", autoescape=True
                            ),
                        )
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            targets = [r for r in rows if r.store_key.rsplit("|v", 1)[0] == identity]
            for row in targets:
                await session.delete(row)
        return bool(targets)

    async def list_eligible(
        self,
        *,
        namespaces: list[MemoryNamespace],
        memory_types: set[MemoryType],
        now: datetime,
    ) -> list[MemoryRecord]:
        if not namespaces or not memory_types:
            return []
        namespace_tuple = tuple_(
            MemoryRecordRow.namespace_scope,
            MemoryRecordRow.namespace_owner,
            MemoryRecordRow.namespace_kind,
        )
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(MemoryRecordRow).where(
                            namespace_tuple.in_(namespaces),
                            MemoryRecordRow.memory_type.in_(
                                [memory_type.value for memory_type in memory_types]
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return sorted(
            (
                record
                for record in current_memories(
                    [MemoryRecord.model_validate(row.payload) for row in rows]
                )
                if record.status is MemoryStatus.ACTIVE
                and (record.expires_at is None or record.expires_at > now)
            ),
            key=lambda record: record.store_key(),
        )

    async def get_many_by_ids(self, memory_ids: list[str]) -> list[MemoryRecord]:
        if not memory_ids:
            return []
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(MemoryRecordRow).where(
                            MemoryRecordRow.memory_id.in_(memory_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
        records: dict[str, MemoryRecord] = {}
        for row in rows:
            record = MemoryRecord.model_validate(row.payload)
            current = records.get(record.id)
            if current is None or (
                record.status is MemoryStatus.ACTIVE,
                record.version,
            ) > (
                current.status is MemoryStatus.ACTIVE,
                current.version,
            ):
                records[record.id] = record
        return [records[memory_id] for memory_id in memory_ids if memory_id in records]

    async def _versions(self, namespace, identity: str) -> list[MemoryRecord]:
        scope, owner, kind = namespace
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(MemoryRecordRow).where(
                            MemoryRecordRow.namespace_scope == scope,
                            MemoryRecordRow.namespace_owner == owner,
                            MemoryRecordRow.namespace_kind == kind,
                            MemoryRecordRow.store_key.startswith(
                                f"{identity}|v", autoescape=True
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return sorted(
            (
                MemoryRecord.model_validate(row.payload)
                for row in rows
                if row.store_key.rsplit("|v", 1)[0] == identity
            ),
            key=lambda record: record.version,
        )
