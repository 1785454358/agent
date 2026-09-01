"""全局研究预算的确定性停止策略。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from deeptrace.config import Settings
from deeptrace.orchestration.state import GraphState
from deeptrace.models import TaskCoverage


def writer_token_reserve(settings: Settings) -> int:
    return int(
        settings.max_api_tokens
        * getattr(settings, "writer_token_reserve_ratio", 0.15)
    )


def verification_token_reserve(settings: Settings) -> int:
    return int(
        settings.max_api_tokens
        * getattr(settings, "verification_token_reserve_ratio", 0.20)
    )


def task_token_allowance(state: GraphState, settings: Settings) -> int:
    plan = state.get("research_plan")
    if plan is None:
        return 0
    remaining = max(1, len(plan.tasks) - state.get("current_task_index", 0))
    pool = max(
        0,
        settings.max_api_tokens
        - writer_token_reserve(settings)
        - verification_token_reserve(settings)
        - state.get("api_token_count", 0),
    )
    return pool // remaining


def task_budget_reason(coverage: TaskCoverage) -> str | None:
    if coverage.api_token_budget and coverage.api_tokens_used >= coverage.api_token_budget:
        return "task_token_budget"
    return None


def elapsed_seconds(started_at: str, now: datetime) -> float:
    started = datetime.fromisoformat(started_at)
    if started.tzinfo is None and now.tzinfo is not None:
        started = started.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - started).total_seconds())


def regular_research_deadline_reached(
    state: GraphState, settings: Settings, now: datetime
) -> bool:
    """为后续核验与写作预留运行时间，仅限制普通研究阶段。"""
    return elapsed_seconds(state["started_at"], now) >= (
        settings.max_runtime_seconds
        * getattr(settings, "research_runtime_ratio", 0.70)
    )


def get_budget_reason(
    state: GraphState, settings: Settings, now: datetime
) -> str | None:
    """按设计优先级返回第一个已触发的全局预算。"""
    if state.get("force_finalize"):
        return "forced_finalize"
    if state.get("step_count", 0) >= settings.hard_max_steps:
        return "step_budget"
    if state.get("fetched_page_count", 0) >= getattr(settings, "max_fetched_pages", 20):
        return "page_budget"
    if state.get("api_token_count", 0) >= getattr(settings, "max_api_tokens", 120_000):
        return "token_budget"
    max_cost: Any = getattr(settings, "max_cost_usd", None)
    if max_cost is not None and Decimal(
        str(state.get("estimated_cost_usd", 0.0))
    ) >= max_cost:
        return "cost_budget"
    if elapsed_seconds(state["started_at"], now) >= getattr(
        settings, "max_runtime_seconds", 600
    ):
        return "time_budget"
    return None
