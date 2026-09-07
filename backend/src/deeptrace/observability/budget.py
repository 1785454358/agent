"""全局研究安全边界的确定性停止策略。"""

from __future__ import annotations

import asyncio
from datetime import datetime

from deeptrace.config import Settings


def elapsed_seconds(started_at: str, now: datetime) -> float:
    started = datetime.fromisoformat(started_at)
    if started.tzinfo is None and now.tzinfo is not None:
        started = started.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - started).total_seconds())


def get_budget_reason(state: dict, settings: Settings, now: datetime) -> str | None:
    """按设计优先级返回第一个已触发的全局预算。"""
    if state.get("force_finalize"):
        return "forced_finalize"
    if state.get("fetched_page_count", 0) >= getattr(settings, "max_fetched_pages", 20):
        return "page_budget"
    return None


class GlobalBudget:
    """单次研究运行的共享预算网关；并行任务通过它竞争全局配额。

    并行工具通过异步锁申请次数配额；耗时、Token 和费用只作统计。
    """

    def __init__(self, settings: Settings, started_at: datetime) -> None:
        self._settings = settings
        self._started_at = started_at
        self._lock = asyncio.Lock()
        self._pages = 0
        self.tool_calls = 0
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
            if self.reason is not None:
                return 0
            allowed = max(
                0,
                getattr(self._settings, "max_fetched_pages", 20) - self._pages,
            )
            granted = min(max(0, requested), allowed)
            self._pages += granted
            return granted

    async def acquire_tool(self) -> bool:
        async with self._lock:
            if self.reason is not None:
                return False
            if self.tool_calls >= getattr(self._settings, "max_tool_calls", 30):
                self.reason = "tool_call_limit"
                return False
            self.tool_calls += 1
            return True

    async def record_usage(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        now: datetime,
    ) -> None:
        """累计 Provider 已返回的用量，不据此停止研究或写作。"""
        async with self._lock:
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
            self._cost_usd += cost_usd

    def stop_reason(self, now: datetime) -> str | None:
        """非阻塞检查全局停止条件；首个触发的预算作为终止原因。"""
        return self.reason
