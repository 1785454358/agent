"""Repository interface and SQLAlchemy implementation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deeptrace.models import AgentResult, RunEvent
from deeptrace.persistence.orm import ResearchRunRow, RunEventRow
from deeptrace.runtime.models import RunRecord, StoredEvent


class RunRepository(Protocol):
    async def create(self, run: RunRecord) -> None: ...

    async def get(self, run_id: str) -> RunRecord | None: ...

    async def list(self, limit: int = 100) -> list[RunRecord]: ...

    async def claim(
        self, run_id: str, worker_id: str, lease_seconds: int
    ) -> RunRecord | None: ...

    async def renew_lease(
        self, run_id: str, worker_id: str, lease_seconds: int
    ) -> bool: ...

    async def append_event(self, run_id: str, event: RunEvent) -> StoredEvent: ...

    async def events_after(
        self, run_id: str, event_id: int, limit: int = 500
    ) -> list[StoredEvent]: ...

    async def request_cancel(self, run_id: str) -> RunRecord | None: ...

    async def complete(
        self, run_id: str, worker_id: str, result: AgentResult
    ) -> RunRecord | None: ...

    async def fail(
        self, run_id: str, worker_id: str, error: str
    ) -> RunRecord | None: ...

    async def cancel(
        self, run_id: str, worker_id: str, error: str
    ) -> RunRecord | None: ...


class SqlAlchemyRunRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, run: RunRecord) -> None:
        async with self._sessions() as session:
            session.add(ResearchRunRow(**run.model_dump(exclude={"events"})))
            await session.commit()

    async def get(self, run_id: str) -> RunRecord | None:
        async with self._sessions() as session:
            row = await session.get(ResearchRunRow, run_id)
            return self._to_record(row) if row is not None else None

    async def list(self, limit: int = 100) -> list[RunRecord]:
        statement = (
            select(ResearchRunRow)
            .order_by(ResearchRunRow.created_at.desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
            return [self._to_record(row) for row in rows]

    async def claim(
        self, run_id: str, worker_id: str, lease_seconds: int
    ) -> RunRecord | None:
        now = datetime.now(UTC)
        statement = (
            update(ResearchRunRow)
            .where(
                ResearchRunRow.id == run_id,
                or_(
                    ResearchRunRow.status == "pending",
                    and_(
                        ResearchRunRow.status == "cancel_requested",
                        or_(
                            ResearchRunRow.lease_owner.is_(None),
                            ResearchRunRow.lease_expires_at < now,
                        ),
                    ),
                    and_(
                        ResearchRunRow.status == "running",
                        ResearchRunRow.lease_expires_at < now,
                    ),
                ),
            )
            .values(
                status="running",
                started_at=now,
                updated_at=now,
                attempt_count=ResearchRunRow.attempt_count + 1,
                version=ResearchRunRow.version + 1,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        async with self._sessions() as session:
            result = await session.execute(statement)
            if result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
        return await self.get(run_id)

    async def renew_lease(
        self, run_id: str, worker_id: str, lease_seconds: int
    ) -> bool:
        now = datetime.now(UTC)
        statement = (
            update(ResearchRunRow)
            .where(
                ResearchRunRow.id == run_id,
                ResearchRunRow.status == "running",
                ResearchRunRow.lease_owner == worker_id,
                ResearchRunRow.lease_expires_at >= now,
            )
            .values(
                updated_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        async with self._sessions() as session:
            result = await session.execute(statement)
            await session.commit()
            return result.rowcount == 1

    async def append_event(self, run_id: str, event: RunEvent) -> StoredEvent:
        created_at = datetime.now(UTC)
        payload = {
            **event.model_dump(mode="json"),
            "ts": created_at.isoformat(),
        }
        row = RunEventRow(
            run_id=run_id,
            event_type=event.event_type,
            payload=payload,
            created_at=created_at,
        )
        async with self._sessions() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return self._to_event(row)

    async def events_after(
        self, run_id: str, event_id: int, limit: int = 500
    ) -> list[StoredEvent]:
        statement = (
            select(RunEventRow)
            .where(RunEventRow.run_id == run_id, RunEventRow.id > event_id)
            .order_by(RunEventRow.id)
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
            return [self._to_event(row) for row in rows]

    async def request_cancel(self, run_id: str) -> RunRecord | None:
        now = datetime.now(UTC)
        statement = (
            update(ResearchRunRow)
            .where(
                ResearchRunRow.id == run_id,
                ResearchRunRow.status.in_(("pending", "running")),
            )
            .values(
                status="cancel_requested",
                updated_at=now,
                version=ResearchRunRow.version + 1,
            )
        )
        async with self._sessions() as session:
            result = await session.execute(statement)
            if result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
        return await self.get(run_id)

    async def complete(
        self, run_id: str, worker_id: str, result: AgentResult
    ) -> RunRecord | None:
        now = datetime.now(UTC)
        usage = {
            "total_tokens": result.provider_usage.total_tokens,
            "input_tokens": result.provider_usage.input_tokens,
            "output_tokens": result.provider_usage.output_tokens,
            "role_usage": result.role_usage.model_dump(mode="json"),
            "steps": result.steps,
            "estimated_cost_usd": (
                str(result.estimated_cost_usd)
                if result.estimated_cost_usd is not None
                else None
            ),
            "stage_seconds": result.stage_seconds,
        }
        statement = (
            update(ResearchRunRow)
            .where(
                ResearchRunRow.id == run_id,
                ResearchRunRow.status == "running",
                ResearchRunRow.lease_owner == worker_id,
            )
            .values(
                status=result.status,
                termination_reason=result.termination_reason,
                answer=result.answer,
                sources=result.sources,
                search_queries=result.search_queries,
                unresolved_gaps=result.unresolved_gaps,
                usage=usage,
                error=None,
                finished_at=now,
                updated_at=now,
                lease_owner=None,
                lease_expires_at=None,
                version=ResearchRunRow.version + 1,
            )
        )
        async with self._sessions() as session:
            update_result = await session.execute(statement)
            if update_result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
        return await self.get(run_id)

    async def fail(
        self, run_id: str, worker_id: str, error: str
    ) -> RunRecord | None:
        return await self._finish_with_error(
            run_id,
            worker_id,
            status="failed",
            termination_reason="worker_error",
            error=error,
            allowed_statuses=("running",),
        )

    async def cancel(
        self, run_id: str, worker_id: str, error: str
    ) -> RunRecord | None:
        return await self._finish_with_error(
            run_id,
            worker_id,
            status="cancelled",
            termination_reason="cancelled",
            error=error,
            allowed_statuses=("running", "cancel_requested"),
        )

    async def _finish_with_error(
        self,
        run_id: str,
        worker_id: str,
        *,
        status: str,
        termination_reason: str,
        error: str,
        allowed_statuses: tuple[str, ...],
    ) -> RunRecord | None:
        now = datetime.now(UTC)
        statement = (
            update(ResearchRunRow)
            .where(
                ResearchRunRow.id == run_id,
                ResearchRunRow.status.in_(allowed_statuses),
                ResearchRunRow.lease_owner == worker_id,
            )
            .values(
                status=status,
                termination_reason=termination_reason,
                error=error,
                finished_at=now,
                updated_at=now,
                lease_owner=None,
                lease_expires_at=None,
                version=ResearchRunRow.version + 1,
            )
        )
        async with self._sessions() as session:
            result = await session.execute(statement)
            if result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
        return await self.get(run_id)

    @staticmethod
    def _to_record(row: ResearchRunRow) -> RunRecord:
        values = {
            column.name: getattr(row, column.name)
            for column in ResearchRunRow.__table__.columns
        }
        for name in (
            "created_at",
            "started_at",
            "finished_at",
            "updated_at",
            "lease_expires_at",
        ):
            value = values[name]
            if value is not None and value.tzinfo is None:
                values[name] = value.replace(tzinfo=UTC)
        return RunRecord.model_validate(values)

    @staticmethod
    def _to_event(row: RunEventRow) -> StoredEvent:
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return StoredEvent(
            id=row.id,
            run_id=row.run_id,
            event_type=row.event_type,
            payload=row.payload,
            created_at=created_at,
        )
