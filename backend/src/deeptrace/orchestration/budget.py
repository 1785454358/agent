"""全局研究安全边界的确定性停止策略。"""

from __future__ import annotations

import asyncio
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


class GlobalBudget:
    """单次研究运行的共享预算网关；并行任务通过它竞争全局配额。

    LangGraph 并行分支各自持有状态副本，页面、费用、时间等全局预算
    不能再依赖 State 计数器。所有跨任务扣减都经过这里的异步锁。
    """

    def __init__(self, settings: Settings, started_at: datetime) -> None:
        self._settings = settings
        self._started_at = started_at
        self._lock = asyncio.Lock()
        self._pages = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost_usd = 0.0
        self.reason: str | None = None

    @property
    def force_finalize(self) -> bool:
        return self.reason is not None

    @property
    def pages_used(self) -> int:
        return self._pages

    async def acquire_pages(self, requested: int, now: datetime) -> int:
        """申请抓取配额，返回实际批准数量；预算耗尽后返回 0。"""
        async with self._lock:
            if self.reason is None:
                self.reason = self._deadline_reason(now)
            if self.reason is not None:
                return 0
            allowed = max(
                0,
                getattr(self._settings, "max_fetched_pages", 20) - self._pages,
            )
            granted = min(max(0, requested), allowed)
            self._pages += granted
            return granted

    async def record_usage(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        now: datetime,
    ) -> None:
        """累计本次运行的真实用量；费用与 token 上限触发后标记全局停止。"""
        async with self._lock:
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
            self._cost_usd += cost_usd
            if self.reason is not None:
                return
            max_cost: Any = getattr(self._settings, "max_cost_usd", None)
            if max_cost is not None and Decimal(str(self._cost_usd)) >= max_cost:
                self.reason = "cost_budget"
                return
            if (
                self._input_tokens + self._output_tokens
                >= getattr(self._settings, "max_total_tokens", 0)
                and getattr(self._settings, "max_total_tokens", 0) > 0
            ):
                self.reason = "token_budget"

    def _deadline_reason(self, now: datetime) -> str | None:
        if elapsed_seconds(self._started_at.isoformat(), now) >= getattr(
            self._settings, "max_runtime_seconds", 600
        ):
            return "time_budget"
        return None

    def stop_reason(self, now: datetime) -> str | None:
        """非阻塞检查全局停止条件；首个触发的预算作为终止原因。"""
        if self.reason is not None:
            return self.reason
        if self._deadline_reason(now) is not None:
            self.reason = "time_budget"
        return self.reason

    def remaining_seconds(self, now: datetime) -> float:
        """返回全局期限剩余秒数；期限到达时同步冻结预算。"""
        if self.stop_reason(now) is not None:
            return 0.0
        elapsed = elapsed_seconds(self._started_at.isoformat(), now)
        return max(
            0.0,
            float(getattr(self._settings, "max_runtime_seconds", 600))
            - elapsed,
        )
