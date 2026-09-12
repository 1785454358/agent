"""Single-process runtime retained for development and lightweight demos."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deeptrace import build_real_agent
from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.models import AgentResult, RunEvent
from deeptrace.runtime.models import RunMode, RunRecord, StoredEvent


_LEGACY_FACTORY_MODES = {
    "workflow": "basic",
    "plan_execute": "deep",
    "multi_agent": "multi_agent",
}


class _LocalRunState:
    def __init__(self, record: RunRecord) -> None:
        self.record = record
        self.task: asyncio.Task[None] | None = None
        self.events: list[StoredEvent] = []
        self.changed = asyncio.Event()


class LocalResearchRuntime:
    def __init__(
        self,
        settings,
        runs_dir: Path | str,
        agent_factory=build_real_agent,
        *,
        application=None,
        context_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._runs_dir = Path(runs_dir)
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._agent_factory = agent_factory
        self._application = application
        self._context_factory = context_factory
        self._registry: dict[str, _LocalRunState] = {}
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

    async def create(self, question: str, mode: RunMode) -> RunRecord:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空")
        now = datetime.now(UTC)
        record = RunRecord(
            id=uuid.uuid4().hex[:12],
            question=clean_question,
            mode=mode,
            created_at=now,
            updated_at=now,
            request_payload={"question": clean_question, "mode": mode},
        )
        state = _LocalRunState(record)
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
        agent = None

        def on_event(event: RunEvent) -> None:
            self._append_event(state, event)

        try:
            if self._application is not None and self._context_factory is not None:
                await self._execute_through_harness(state)
                return
            agent = self._agent_factory(
                self._settings,
                on_event=on_event,
                mode=_LEGACY_FACTORY_MODES.get(record.mode, record.mode),
            )
            result = await agent.arun(record.question)
            self._apply_result(record, result)
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
            if agent is not None:
                await agent.aclose()
            record.updated_at = datetime.now(UTC)
            self._persist(record)
            self._append_done(state)

    async def _execute_through_harness(self, state: _LocalRunState) -> None:
        record = state.record
        context = self._context_factory(record.id)
        request = ApplicationResearchRequest(
            run_id=record.id,
            thread_id=record.id,
            question=record.question,
            mode=record.mode,
        )
        outcome = await self._application.invoke(
            request,
            config={"configurable": {"thread_id": record.id}},
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

    @staticmethod
    def _apply_result(record: RunRecord, result: AgentResult) -> None:
        record.status = result.status
        record.termination_reason = result.termination_reason
        record.finished_at = datetime.now(UTC)
        record.answer = result.answer
        record.sources = result.sources
        record.search_queries = result.search_queries
        record.unresolved_gaps = result.unresolved_gaps
        record.usage = {
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
