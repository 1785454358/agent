"""Single-process runtime retained for development and lightweight demos."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.runtime.errors import ThreadBusyError
from deeptrace.models import RunEvent
from deeptrace.runtime.models import RunMode, RunRecord, StoredEvent


class _LocalRunState:
    def __init__(self, record: RunRecord) -> None:
        self.record = record
        self.task: asyncio.Task[None] | None = None
        self.events: list[StoredEvent] = []
        self.changed = asyncio.Event()
        self.thread_lock: asyncio.Lock | None = None


class LocalResearchRuntime:
    def __init__(
        self,
        settings,
        runs_dir: Path | str,
        *,
        application,
        context_factory: Callable[[str], Any],
    ) -> None:
        self._settings = settings
        self._runs_dir = Path(runs_dir)
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._application = application
        self._context_factory = context_factory
        self._registry: dict[str, _LocalRunState] = {}
        self._thread_locks: dict[str, asyncio.Lock] = {}
        self._next_event_id = 1

    async def start(self) -> None:
        self._runs_dir.mkdir(parents=True, exist_ok=True)

    async def stop(self) -> None:
        tasks = [
            state.task
            for state in self._registry.values()
            if state.task is not None and not state.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def create(
        self, question: str, mode: RunMode, thread_id: str | None = None
    ) -> RunRecord:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空")
        now = datetime.now(UTC)
        clean_thread = (thread_id or "").strip()
        thread_key = clean_thread or uuid.uuid4().hex[:12]
        lock = self._thread_locks.setdefault(thread_key, asyncio.Lock())
        if lock.locked():
            raise ThreadBusyError(thread_key)
        await lock.acquire()
        record = RunRecord(
            id=uuid.uuid4().hex[:12],
            question=clean_question,
            mode=mode,
            thread_id=thread_key,
            created_at=now,
            updated_at=now,
            request_payload={
                "question": clean_question,
                "mode": mode,
                "thread_id": clean_thread or None,
            },
        )
        state = _LocalRunState(record)
        state.thread_lock = lock
        self._registry[record.id] = state
        state.task = asyncio.create_task(self._execute(state))
        self._persist(record)
        return record

    async def get(self, run_id: str) -> RunRecord | None:
        state = self._registry.get(run_id)
        return state.record if state is not None else None

    async def list(self) -> list[RunRecord]:
        return sorted(
            (state.record for state in self._registry.values()),
            key=lambda record: record.created_at,
            reverse=True,
        )

    async def cancel(self, run_id: str) -> RunRecord | None:
        state = self._registry.get(run_id)
        if state is None:
            return None
        if state.task is not None and not state.task.done():
            state.task.cancel()
            await asyncio.gather(state.task, return_exceptions=True)
        return state.record

    async def events(self, run_id: str, after_event_id: int = 0):
        state = self._registry.get(run_id)
        if state is None:
            return
        cursor = after_event_id
        while True:
            state.changed.clear()
            pending = [event for event in state.events if event.id > cursor]
            if pending:
                for event in pending:
                    cursor = event.id
                    yield event
                    if event.event_type == "done":
                        return
                continue
            await state.changed.wait()

    async def _execute(self, state: _LocalRunState) -> None:
        record = state.record
        now = datetime.now(UTC)
        record.status = "running"
        record.started_at = now
        record.updated_at = now

        try:
            await self._execute_through_harness(state)
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.termination_reason = "cancelled"
            record.finished_at = datetime.now(UTC)
            record.error = "运行被用户取消"
            raise
        except Exception as exc:
            record.status = "failed"
            record.termination_reason = "worker_error"
            record.finished_at = datetime.now(UTC)
            record.error = f"运行失败（{type(exc).__name__}），请检查服务与模型配置"
        finally:
            record.updated_at = datetime.now(UTC)
            self._persist(record)
            self._append_done(state)
            if state.thread_lock is not None:
                state.thread_lock.release()

    async def _execute_through_harness(self, state: _LocalRunState) -> None:
        record = state.record

        def on_harness_event(event_type: str, payload: dict) -> None:
            self._append_event(
                state,
                RunEvent(
                    event_type=event_type,
                    message=str(payload.get("error_code") or event_type),
                ),
            )

        context = self._context_factory(record.id, on_harness_event)
        thread_id = record.thread_id or record.id
        request = ApplicationResearchRequest(
            run_id=record.id,
            thread_id=thread_id,
            question=record.question,
            mode=record.mode,
        )
        outcome = await self._application.invoke(
            request,
            config={"configurable": {"thread_id": thread_id}},
            context=context,
        )
        record.answer = outcome.content
        record.status = "completed" if outcome.partial_reason is None else "partial"
        record.termination_reason = outcome.partial_reason or "completed"
        record.finished_at = datetime.now(UTC)
        evidence = await context.evidence_store.get_many(
            context.workspace_id, outcome.cited_evidence_ids
        )
        record.sources = [item.canonical_url for item in evidence]
        self._append_event(
            state,
            RunEvent(
                event_type="response.completed",
                message="研究已完成",
            ),
        )

    def _persist(self, record: RunRecord) -> None:
        path = self._runs_dir / f"{record.id}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def _append_event(self, state: _LocalRunState, event: RunEvent) -> None:
        created_at = datetime.now(UTC)
        payload = {
            **event.model_dump(mode="json"),
            "ts": created_at.isoformat(),
        }
        state.record.events.append(payload)
        self._append_stored(
            state,
            StoredEvent(
                id=self._take_event_id(),
                run_id=state.record.id,
                event_type=event.event_type,
                payload=payload,
                created_at=created_at,
            ),
        )

    def _append_done(self, state: _LocalRunState) -> None:
        self._append_stored(
            state,
            StoredEvent(
                id=self._take_event_id(),
                run_id=state.record.id,
                event_type="done",
                payload={},
                created_at=datetime.now(UTC),
            ),
        )

    def _append_stored(self, state: _LocalRunState, event: StoredEvent) -> None:
        state.events.append(event)
        state.changed.set()

    def _take_event_id(self) -> int:
        event_id = self._next_event_id
        self._next_event_id += 1
        return event_id
