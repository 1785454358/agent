"""Worker-shaped entry point that runs the top-level graph with real identity."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings
from deeptrace.models import AgentResult, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.observability.messages import (
    humanize_event_message,
    public_event_details,
)
from deeptrace.observability.model_metrics import run_usage_payload
from deeptrace.runtime.models import RunRecord


class HarnessResearchRunner:
    """Runs one persisted run through the top-level graph.

    The run's database identity (``run.id`` and ``run.thread_id``) is passed
    unchanged into the application service, so checkpoints, the tool ledger
    and SSE/run records all share one authoritative identity across retries.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bundle: Any | None = None

    def _ensure_bundle(self):
        if self._bundle is None:
            from deeptrace.application.assembly import build_harness_runtime

            self._bundle = build_harness_runtime(self._settings)
        return self._bundle

    async def aclose(self) -> None:
        if self._bundle is not None:
            await self._bundle.aclose()
            self._bundle = None

    async def __call__(
        self,
        run: RunRecord,
        on_event: Callable[[RunEvent], None] | None = None,
    ) -> AgentResult:
        bundle = self._ensure_bundle()
        thread_id = run.thread_id or run.id

        def emit(event_type: str, message: str) -> None:
            if on_event is None:
                return
            try:
                on_event(RunEvent(event_type=event_type, message=message))
            except Exception:  # noqa: BLE001 - observers cannot abort execution
                return

        def on_harness_event(event_type: str, payload: dict) -> None:
            details = public_event_details(payload)
            if on_event is None:
                return
            try:
                on_event(
                    RunEvent(
                        event_type=event_type,
                        message=humanize_event_message(event_type, details),
                        details=details,
                    )
                )
            except Exception:  # noqa: BLE001 - observers cannot abort execution
                return

        context = None
        try:
            context = bundle.context_factory(run.id, on_harness_event)
            emit("run.started", "研究任务已进入统一运行图")
            outcome = await bundle.service.invoke(
                ApplicationResearchRequest(
                    run_id=run.id,
                    thread_id=thread_id,
                    question=run.question,
                    mode=run.mode,
                ),
                config={"configurable": {"thread_id": thread_id}},
                context=context,
            )
        finally:
            run.usage = run_usage_payload(context)
            release = getattr(bundle, "release_run", None)
            if release is not None:
                release(run.id)
        usage = run.usage
        emit(
            "response.completed",
            {"completed": "研究已完成", "partial": "研究部分完成",
             "failed": "研究失败", "cancelled": "研究已取消"}[outcome.status],
        )
        return AgentResult(
            status=outcome.status,
            answer=outcome.response_outcome.content if outcome.response_outcome is not None else "",
            sources=outcome.sources,
            steps=outcome.executed_steps,
            events=[],
            termination_reason=outcome.termination_reason,
            search_queries=[],
            provider_usage=TokenUsage.model_validate(usage["observed_usage"])
            if usage
            else TokenUsage(),
            role_usage=UsageBreakdown.model_validate(usage["role_usage"])
            if usage
            else UsageBreakdown(),
            estimated_cost_usd=None,
            stage_seconds=usage["stage_seconds"] if usage else {},
            unresolved_gaps=outcome.unresolved_gaps,
            usage_observation=usage,
            research_sufficiency=outcome.research_sufficiency,
        )


def build_harness_runner(settings: Settings) -> HarnessResearchRunner:
    return HarnessResearchRunner(settings)
