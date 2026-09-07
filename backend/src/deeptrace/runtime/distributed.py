"""API-side runtime backed by durable storage and a Redis broker."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from deeptrace.persistence.repository import RunRepository
from deeptrace.queue.protocol import ResearchBroker
from deeptrace.runtime.models import RunMode, RunRecord


class JobDispatchError(RuntimeError):
    """The durable run exists but its queue dispatch failed."""


class DistributedResearchRuntime:
    def __init__(
        self,
        repository: RunRepository,
        broker: ResearchBroker,
        *,
        id_factory=lambda: uuid.uuid4().hex[:12],
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._id_factory = id_factory

    async def start(self) -> None:
        await self._broker.ensure_group()

    async def create(self, question: str, mode: RunMode) -> RunRecord:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空")
        now = datetime.now(UTC)
        run = RunRecord(
            id=self._id_factory(),
            question=clean_question,
            mode=mode,
            created_at=now,
            updated_at=now,
            request_payload={"question": clean_question, "mode": mode},
        )
        await self._repository.create(run)
        try:
            await self._broker.enqueue(run.id)
        except Exception as exc:
            raise JobDispatchError(f"failed to enqueue run {run.id}") from exc
        return run

    async def get(self, run_id: str) -> RunRecord | None:
        run = await self._repository.get(run_id)
        if run is None:
            return None
        events = await self._repository.events_after(run_id, 0, limit=200)
        run.events = [event.payload for event in events]
        return run

    async def list(self) -> list[RunRecord]:
        return await self._repository.list()

    async def cancel(self, run_id: str) -> RunRecord | None:
        run = await self._repository.request_cancel(run_id)
        if run is None:
            return await self._repository.get(run_id)
        await self._broker.request_cancel(run_id)
        return run
