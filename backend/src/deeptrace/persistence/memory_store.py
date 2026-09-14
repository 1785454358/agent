"""SQL-backed long-term memory store over the memory_records table."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType
from deeptrace.domain.memory import MemoryNamespace
from deeptrace.persistence.orm import MemoryRecordRow


class SqlAlchemyMemoryStore:
    """Same semantics as InMemoryMemoryStore, persisted across restarts.

    One row per record version; ``get`` returns the latest active version for
    the identity, superseded versions stay queryable for the audit trail.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._lock = asyncio.Lock()

    async def put(self, record: MemoryRecord) -> MemoryRecord:
        if not isinstance(record, MemoryRecord):
            raise TypeError("record must be a MemoryRecord")
        scope, owner, kind = record.namespace
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(MemoryRecordRow).where(
                        MemoryRecordRow.namespace_scope == scope,
                        MemoryRecordRow.namespace_owner == owner,
                        MemoryRecordRow.namespace_kind == kind,
                        MemoryRecordRow.store_key == record.store_key(),
                    )
                )
            ).scalar_one_or_none()
            payload = record.model_dump(mode="json")
            if row is None:
                session.add(
                    MemoryRecordRow(
                        namespace_scope=scope,
                        namespace_owner=owner,
                        namespace_kind=kind,
                        store_key=record.store_key(),
                        memory_id=record.id,
                        memory_type=record.type.value,
                        status=record.status.value,
                        importance=record.importance,
                        confidence=record.confidence,
                        created_at=record.created_at,
                        expires_at=record.expires_at,
                        payload=payload,
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                row.memory_id = record.id
                row.memory_type = record.type.value
                row.status = record.status.value
                row.importance = record.importance
                row.confidence = record.confidence
                row.created_at = record.created_at
                row.expires_at = record.expires_at
                row.payload = payload
                row.updated_at = datetime.now(UTC)
            await session.commit()
        return record.model_copy(deep=True)

    async def get(self, namespace, identity: str) -> MemoryRecord | None:
        versions = await self._versions(namespace, identity)
        if not versions:
            return None
        active = [r for r in versions if r.status.value == "active"]
        pool = active or versions
        return max(pool, key=lambda record: record.version).model_copy(deep=True)

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
                for record in records
                if record.status.value in {"active", "stale", "candidate"}
            ),
            key=lambda record: record.store_key(),
        )

    async def delete(self, namespace, identity: str) -> bool:
        scope, owner, kind = namespace
        async with self._sessions() as session:
            result = await session.execute(
                delete(MemoryRecordRow).where(
                    MemoryRecordRow.namespace_scope == scope,
                    MemoryRecordRow.namespace_owner == owner,
                    MemoryRecordRow.namespace_kind == kind,
                    MemoryRecordRow.store_key.like(f"{identity}|v%"),
                )
            )
            await session.commit()
        return bool(result.rowcount)

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
                            MemoryRecordRow.status.in_(
                                [
                                    MemoryStatus.ACTIVE.value,
                                    MemoryStatus.STALE.value,
                                ]
                            ),
                            or_(
                                MemoryRecordRow.expires_at.is_(None),
                                MemoryRecordRow.expires_at > now,
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return sorted(
            (MemoryRecord.model_validate(row.payload) for row in rows),
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

    async def _versions(
        self, namespace, identity: str
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
                            MemoryRecordRow.store_key.like(f"{identity}|v%"),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return sorted(
            (MemoryRecord.model_validate(row.payload) for row in rows),
            key=lambda record: record.version,
        )
