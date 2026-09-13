"""API-side runtime backed by durable storage and a Redis broker."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from deeptrace.persistence.repository import RunRepository
from deeptrace.queue.protocol import ResearchBroker
from deeptrace.runtime.errors import ThreadBusyError
from deeptrace.runtime.models import RunMode, RunRecord

TERMINAL_STATUSES = {"completed", "partial", "failed", "cancelled"}


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

    async def stop(self) -> None:
        await self._broker.aclose()

    async def create(
        self, question: str, mode: RunMode, thread_id: str | None = None
    ) -> RunRecord:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空")
        clean_thread = (thread_id or "").strip()
        now = datetime.now(UTC)
        run = RunRecord(
            id=self._id_factory(),
            question=clean_question,
            mode=mode,
            thread_id=clean_thread or self._id_factory(),
            created_at=now,
            updated_at=now,
            request_payload={
                "question": clean_question,
                "mode": mode,
                "thread_id": clean_thread or None,
            },
        )
        # Atomic thread claim: the INSERT-based lease guarantees one active run
        # per thread even across API processes.
        if not await self._repository.acquire_thread_lease(
            run.thread_id, run.id
        ):
            raise ThreadBusyError(run.thread_id)
        try:
            await self._repository.create(run)
            await self._broker.enqueue(run.id)
        except Exception as exc:
            await self._repository.release_thread_lease(run.thread_id, run.id)
            if isinstance(exc, JobDispatchError):
                raise
            raise JobDispatchError(
                f"failed to dispatch run {run.id}"
            ) from exc
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

    async def events(self, run_id: str, after_event_id: int = 0):
        cursor = after_event_id
        async with self._broker.subscription(run_id) as notifications:
            while True:
                events = await self._repository.events_after(run_id, cursor)
                if events:
                    for event in events:
                        cursor = event.id
                        yield event
                        if event.event_type == "done":
                            return
                    continue

                run = await self._repository.get(run_id)
                if run is None:
                    return
                if run.status in TERMINAL_STATUSES:
                    return
                try:
                    await anext(notifications)
                except StopAsyncIteration:
                    return
