"""Worker-shaped entry point that runs the top-level graph with real identity."""

from __future__ import annotations

from typing import Any, Callable

from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings
from deeptrace.models import AgentResult, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.runtime.models import RunRecord


class HarnessResearchRunner:
    """Runs one persisted run through the top-level graph.

    The run's database identity (``run.id`` and ``run.thread_id``) is passed
    unchanged into the application service, so checkpoints, the tool ledger
    and SSE/run records all share one authoritative identity across retries.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runtime: tuple[Any, Callable[[str], Any]] | None = None

    def _ensure_runtime(self):
        if self._runtime is None:
            from deeptrace.application.assembly import build_harness_runtime

            self._runtime = build_harness_runtime(self._settings)
        return self._runtime

    async def __call__(
        self,
        run: RunRecord,
        on_event: Callable[[RunEvent], None] | None = None,
    ) -> AgentResult:
        service, context_factory = self._ensure_runtime()
        thread_id = run.thread_id or run.id

        def emit(event_type: str, message: str) -> None:
            if on_event is None:
                return
            try:
                on_event(RunEvent(event_type=event_type, message=message))
            except Exception:
                return

        def on_harness_event(event_type: str, payload: dict) -> None:
            emit(event_type, str(payload.get("error_code") or event_type))

        context = context_factory(run.id, on_harness_event)
        emit("planning.completed", "研究任务已进入统一运行图")
        outcome = await service.invoke(
            ApplicationResearchRequest(
                run_id=run.id,
                thread_id=thread_id,
                question=run.question,
                mode=run.mode,
            ),
            config={"configurable": {"thread_id": thread_id}},
            context=context,
        )
        sources: list[str] = []
        if outcome.cited_evidence_ids:
            evidence = await context.evidence_store.get_many(
                context.workspace_id, outcome.cited_evidence_ids
            )
            sources = [item.canonical_url for item in evidence]
        emit(
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


def build_harness_runner(settings: Settings) -> HarnessResearchRunner:
    return HarnessResearchRunner(settings)
