"""Run accounting and fair network-attempt leases for Multi-Agent research."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from deeptrace.models import RunEvent, UsageBreakdown, add_token_usages, message_usage


class ToolLease:
    """A task-local view of capacity reserved by the run quota manager."""

    def __init__(self, manager: QuotaManager, task_id: str, limit: int) -> None:
        self._manager = manager
        self.task_id = task_id
        self.limit = limit
        self.used = 0
        self._released = False

    async def acquire_network(self) -> bool:
        return await self._manager._acquire(self)

    async def release(self) -> None:
        await self._manager._release(self)


class QuotaManager:
    """Reserve task capacity while charging only actual network attempts."""

    def __init__(
        self, *, total: int, per_researcher: int, reserve_ratio: float = 0.2
    ) -> None:
        if total < 1 or per_researcher < 1:
            raise ValueError("tool limits must be positive")
        if not 0 <= reserve_ratio < 1:
            raise ValueError("reserve ratio must be in [0, 1)")
        self.total = total
        self.per_researcher = per_researcher
        self.reserved = int(total * reserve_ratio)
        self._free = total - self.reserved
        self.consumed = 0
        self._lock = asyncio.Lock()
        self._initial_allocated = False
        self._leases: dict[str, ToolLease] = {}

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.consumed)

    @staticmethod
    def _limits(capacity: int, count: int, per_researcher: int) -> list[int]:
        allocatable = min(capacity, count * per_researcher)
        base, extra = divmod(allocatable, count)
        return [min(per_researcher, base + (1 if index < extra else 0)) for index in range(count)]

    async def allocate_initial(self, task_ids: list[str]) -> dict[str, ToolLease]:
        if not task_ids or len(task_ids) != len(set(task_ids)):
            raise ValueError("task IDs must be non-empty and unique")
        async with self._lock:
            if self._initial_allocated:
                raise RuntimeError("initial quota was already allocated")
            self._initial_allocated = True
            limits = self._limits(self._free, len(task_ids), self.per_researcher)
            self._free -= sum(limits)
            return self._create_leases(task_ids, limits)

    async def allocate_follow_up(self, task_ids: list[str]) -> dict[str, ToolLease]:
        if not task_ids or len(task_ids) != len(set(task_ids)):
            raise ValueError("task IDs must be non-empty and unique")
        async with self._lock:
            if any(task_id in self._leases for task_id in task_ids):
                raise ValueError("task ID already has a lease")
            self._free += self.reserved
            self.reserved = 0
            usable = min(self._free, self.remaining)
            limits = self._limits(usable, len(task_ids), self.per_researcher)
            self._free -= sum(limits)
            return self._create_leases(task_ids, limits)

    def _create_leases(
        self, task_ids: list[str], limits: list[int]
    ) -> dict[str, ToolLease]:
        created = {
            task_id: ToolLease(self, task_id, limit)
            for task_id, limit in zip(task_ids, limits, strict=True)
        }
        self._leases.update(created)
        return created

    async def _acquire(self, lease: ToolLease) -> bool:
        async with self._lock:
            if lease._released or lease.used >= lease.limit or self.consumed >= self.total:
                return False
            lease.used += 1
            self.consumed += 1
            return True

    async def _release(self, lease: ToolLease) -> None:
        async with self._lock:
            if lease._released:
                return
            lease._released = True
            self._free += max(0, lease.limit - lease.used)


class MultiAgentRuntime:
    """Per-run events, Provider usage, and observed stage duration."""

    def __init__(self, settings: Any, on_event=None) -> None:
        self.settings = settings
        self.on_event = on_event
        self.started = time.monotonic()
        self.steps = 0
        self.events: list[RunEvent] = []
        self.role_usage = UsageBreakdown()
        self.stage_seconds: dict[str, float] = {}

    def emit(self, event_type: str, message: str, **details) -> None:
        event = RunEvent(event_type=event_type, message=message, details=details)
        self.events.append(event)
        if self.on_event:
            self.on_event(event)

    def account(self, role: str, usage) -> None:
        current = getattr(self.role_usage, role)
        setattr(self.role_usage, role, add_token_usages(current, usage))

    async def invoke(self, model, messages, role: str):
        timeout = float(
            getattr(self.settings, "multi_agent_call_timeout_seconds", 45)
        )
        self.steps += 1
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(model.ainvoke(messages), timeout=timeout)
            self.account(role, message_usage(response))
            return response
        finally:
            self.stage_seconds[role] = self.stage_seconds.get(role, 0.0) + (
                time.monotonic() - started
            )
