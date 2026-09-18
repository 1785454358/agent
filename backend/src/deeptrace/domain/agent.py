"""Explicit result of every controlled exit from the shared agent runtime."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deeptrace.domain.execution import BudgetSnapshot, ErrorRecord


class AgentOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "partial", "failed", "cancelled"]
    stop_reason: Literal[
        "completed",
        "iteration_limit",
        "error_limit",
        "budget_exhausted",
        "context_limit",
        "model_error",
        "tool_error",
        "incomplete_plan",
        "cancelled",
    ]
    summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    errors: list[ErrorRecord] = Field(default_factory=list)
    iterations: int = Field(default=0, ge=0)
    executed_steps: int = Field(default=0, ge=0)
    budget: BudgetSnapshot = Field(default_factory=BudgetSnapshot)
    unfinished_todos: list[str] = Field(default_factory=list)
    plan_total: int = Field(default=0, ge=0)
    plan_completed: int = Field(default=0, ge=0)
