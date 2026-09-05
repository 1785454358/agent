"""Per-run deadline, events, and usage accounting for every research role."""

import asyncio
import time
from typing import Any

from deeptrace.agent._shared import message_usage
from deeptrace.models import RunEvent, UsageBreakdown, add_token_usages
from deeptrace.observability import estimate_usage_cost


class ResearchStopped(Exception):
    """A deterministic stop, never a Provider error to retry."""


class RunRuntime:
    def __init__(self, settings: Any, on_event=None):
        self.settings = settings
        self.on_event = on_event
        self.started = time.monotonic()
        duration = float(settings.max_runtime_seconds or 600)
        self.deadline = self.started + duration
        reserve = min(float(settings.writer_timeout_seconds), duration / 4)
        self.research_deadline = self.deadline - reserve
        self.role_usage = UsageBreakdown()
        self.events: list[RunEvent] = []
        self.steps = 0
        self.stage_seconds: dict[str, float] = {}

    def remaining(self, research=True) -> float:
        deadline = self.research_deadline if research else self.deadline
        return max(0.0, deadline - time.monotonic())

    def check(self, research=True) -> None:
        if self.remaining(research) <= 0:
            raise ResearchStopped("time_budget")
        if self.role_usage.total.total_tokens >= getattr(
            self.settings, "deep_max_tokens", 40000
        ):
            raise ResearchStopped("token_budget")
        cost = estimate_usage_cost(
            self.role_usage.total,
            getattr(self.settings, "input_cost_per_million", None),
            getattr(self.settings, "output_cost_per_million", None),
        )
        limit = getattr(self.settings, "max_cost_usd", None)
        if limit is not None and cost is not None and cost >= limit:
            raise ResearchStopped("cost_budget")

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
        self.check()
        timeout = min(
            self.remaining(),
            float(getattr(self.settings, "deep_call_timeout_seconds", 45)),
        )
        self.steps += 1
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(model.ainvoke(messages), timeout=timeout)
            self.account(role, message_usage(response))
            return response
        except TimeoutError:
            if self.remaining() <= 0:
                raise ResearchStopped("time_budget") from None
            raise
        finally:
            self.stage_seconds[role] = (
                self.stage_seconds.get(role, 0) + time.monotonic() - started
            )
