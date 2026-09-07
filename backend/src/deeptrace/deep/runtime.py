"""Per-run tool quota, events, and observational usage accounting."""

import asyncio
import time
from typing import Any

from deeptrace.models import RunEvent, UsageBreakdown, add_token_usages, message_usage


class RunRuntime:
    def __init__(self, settings: Any, on_event=None):
        self.settings = settings
        self.on_event = on_event
        self.started = time.monotonic()
        self.role_usage = UsageBreakdown()
        self.events: list[RunEvent] = []
        self.steps = 0
        self.tool_calls = 0
        self.stage_seconds: dict[str, float] = {}

    def remaining_tools(self) -> int:
        return max(
            0, getattr(self.settings, "deep_max_tool_calls", 30) - self.tool_calls
        )

    def claim_tool(self) -> bool:
        # No await between checking and incrementing: parallel coroutines share
        # this quota atomically on the run's event loop.
        if not self.remaining_tools():
            return False
        self.tool_calls += 1
        return True

    def emit(self, event_type: str, message: str, **details) -> None:
        event = RunEvent(event_type=event_type, message=message, details=details)
        self.events.append(event)
        if self.on_event:
            self.on_event(event)

    def account(self, role: str, usage) -> None:
        setattr(
            self.role_usage,
            role,
            add_token_usages(getattr(self.role_usage, role), usage),
        )

    async def invoke(self, model, messages, role: str):
        timeout = float(getattr(self.settings, "deep_call_timeout_seconds", 45))
        self.steps += 1
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(model.ainvoke(messages), timeout=timeout)
            self.account(role, message_usage(response))
            return response
        finally:
            self.stage_seconds[role] = (
                self.stage_seconds.get(role, 0) + time.monotonic() - started
            )
