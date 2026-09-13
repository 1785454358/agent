"""SQL-backed long-term memory store over the memory_records table."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deeptrace.domain import MemoryRecord
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
                        payload=payload,
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
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
