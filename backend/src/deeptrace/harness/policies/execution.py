"""Pure continuation and exit decisions for every orchestration strategy."""

from dataclasses import dataclass
from typing import Literal

from deeptrace.domain import BudgetSnapshot
from deeptrace.domain.agent import AgentOutcome, AgentStatus, AgentStopReason
from deeptrace.harness.agent_state import AgentExecutorState, TodoStatus


@dataclass(frozen=True)
class ExecutionPolicy:
    max_iterations: int = 8
    consecutive_error_limit: int = 3
    completion_nudge_limit: int = 2

    def __post_init__(self):
        if (
            self.max_iterations < 1
            or self.consecutive_error_limit < 1
            or self.completion_nudge_limit < 0
        ):
            raise ValueError("Invalid execution limits")

    def stop(
        self, state: AgentExecutorState, *, model_finished: bool = False
    ) -> AgentStopReason | Literal[""]:
        if state.get("stop_reason"):
            return state["stop_reason"]
        open_items = [
            t for t in state.get("todos", []) if t.status != TodoStatus.COMPLETED
        ]
        if model_finished and state.get("evidence_ids") and not open_items:
            return "completed"
        if state.get("consecutive_errors", 0) >= self.consecutive_error_limit:
            return "error_limit"
        if state.get("iteration", 0) >= self.max_iterations:
            return "iteration_limit"
        if (
            model_finished
            and state.get("completion_nudges", 0) >= self.completion_nudge_limit
        ):
            return "incomplete_plan"
        return ""

    def outcome(self, state: AgentExecutorState) -> AgentOutcome:
        reason = state.get("stop_reason") or "incomplete_plan"
        evidence = sorted(set(state.get("evidence_ids") or []))
        todos = state.get("todos") or []
        unfinished = [t.content for t in todos if t.status != TodoStatus.COMPLETED]
        status: AgentStatus = "partial"
        if reason in {"completed", "cancelled"}:
            status = reason
        elif not evidence and reason in {"model_error", "tool_error", "context_limit"}:
            status = "failed"
        summary = state.get("completion_summary") or next(
            (
                str(m.content)
                for m in reversed(state.get("messages") or [])
                if m.type == "ai" and not getattr(m, "tool_calls", [])
            ),
            "",
        )
        return AgentOutcome(
            status=status,
            stop_reason=reason,
            summary=summary,
            evidence_ids=evidence,
            errors=state.get("failures") or [],
            iterations=state.get("iteration", 0),
            executed_steps=state.get("executed_steps", 0),
            unfinished_todos=unfinished,
            plan_total=len(todos),
            plan_completed=len(todos) - len(unfinished),
            budget=BudgetSnapshot(
                max_model_calls=self.max_iterations,
                used_model_calls=state.get("iteration", 0),
                used_tool_calls=state.get("executed_steps", 0),
            ),
        )
