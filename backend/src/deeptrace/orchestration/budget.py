"""全局研究预算的确定性停止策略。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from deeptrace.config import Settings
from deeptrace.orchestration.state import GraphState


def elapsed_seconds(started_at: str, now: datetime) -> float:
    started = datetime.fromisoformat(started_at)
    if started.tzinfo is None and now.tzinfo is not None:
        started = started.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - started).total_seconds())


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
