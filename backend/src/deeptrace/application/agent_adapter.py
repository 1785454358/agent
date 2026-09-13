"""Agent-shaped adapter so Worker/CLI run on the top-level runtime graph."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable

from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings
from deeptrace.models import AgentResult, RunEvent, TokenUsage, UsageBreakdown


class HarnessRunAdapter:
    """Same ``arun``/``aclose`` surface as the legacy agents, harness inside."""

    def __init__(
        self,
        service,
        context_factory: Callable[[str], Any],
        *,
        run_id: str,
        thread_id: str,
        mode: str,
        on_event: Callable[[RunEvent], None] | None = None,
    ) -> None:
        self._service = service
        self._context_factory = context_factory
        self._run_id = run_id
        self._thread_id = thread_id
        self._mode = mode
        self._on_event = on_event
        self._context: Any = None

    def _emit(self, event_type: str, message: str) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(RunEvent(event_type=event_type, message=message))
        except Exception:
            return

    async def arun(self, question: str) -> AgentResult:
        self._context = self._context_factory(self._run_id)
        self._emit("planning.completed", "研究任务已进入统一运行图")
        outcome = await self._service.invoke(
            ApplicationResearchRequest(
                run_id=self._run_id,
                thread_id=self._thread_id,
                question=question,
                mode=self._mode,  # type: ignore[arg-type]
            ),
            config={"configurable": {"thread_id": self._thread_id}},
            context=self._context,
        )
        sources: list[str] = []
        if outcome.cited_evidence_ids:
            evidence = await self._context.evidence_store.get_many(
                self._context.workspace_id, outcome.cited_evidence_ids
            )
            sources = [item.canonical_url for item in evidence]
        self._emit(
            "response.completed",
            "研究已完成" if outcome.partial_reason is None else "研究部分完成",
        )
        status = "completed" if outcome.partial_reason is None else "partial"
        return AgentResult(
            status=status,  # type: ignore[arg-type]
            answer=outcome.content,
            sources=sources,
            steps=1,
            events=[],
            termination_reason=outcome.partial_reason or "completed",
            search_queries=[],
            provider_usage=TokenUsage(),
            role_usage=UsageBreakdown(),
            estimated_cost_usd=None,
            stage_seconds={},
            unresolved_gaps=[],
        )

    async def aclose(self) -> None:
        return None


class HarnessAgentFactory:
    """Builds HarnessRunAdapter instances on one cached shared runtime."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runtime: tuple[Any, Callable[[str], Any]] | None = None

    def __call__(self, settings: Settings, on_event=None, mode: str = "workflow"):
        if self._runtime is None:
            from deeptrace.application.assembly import build_harness_runtime

            self._runtime = build_harness_runtime(settings)
        service, context_factory = self._runtime
        run_id = uuid.uuid4().hex[:12]
        return HarnessRunAdapter(
            service,
            context_factory,
            run_id=run_id,
            thread_id=run_id,
            mode=mode,
            on_event=on_event,
        )


def build_harness_agent_factory(settings: Settings) -> HarnessAgentFactory:
    return HarnessAgentFactory(settings)
