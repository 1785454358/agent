"""Shared admission control for one run, including concurrent research branches."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from deeptrace.domain import ErrorCategory
from deeptrace.harness.policies.agent_context import message_tokens


class ModelBudgetExceeded(RuntimeError):
    code = "budget_exhausted"
    category = ErrorCategory.PARTIAL

    def __init__(self, reason: str):
        super().__init__("budget_exhausted:" + reason)


class RunBudgetModelGateway:
    """Reserve before dispatch; charge provider input usage when it is available.

    Missing usage and failed transports retain the estimated input reservation.
    The counters cover gateway dispatches; use a one-attempt underlying gateway
    to make that equivalent to provider requests. This state lives for a run in
    one process; it is deliberately not advertised as a durable billing ledger.
    """

    def __init__(
        self, inner, *, max_calls: int = 20, max_input_tokens: int = 100_000,
        finishing_input_reserve: int = 20_000, max_seconds: float = 600,
        finishing_seconds: float = 120,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        if (
            max_calls < 3
            or not 0 <= finishing_input_reserve < max_input_tokens
            or max_seconds <= 0
            or finishing_seconds <= 0
        ):
            raise ValueError("Invalid model run limits")
        self.inner = inner
        self.max_calls = max_calls
        self.max_input_tokens = max_input_tokens
        self.finishing_input_reserve = finishing_input_reserve
        self.max_seconds = max_seconds
        self.finishing_seconds = finishing_seconds
        self._clock = monotonic
        self._started = monotonic()
        self._lock = asyncio.Lock()
        self.used_calls = 0
        self.used_input_tokens = 0
        self._reserved_input = 0

    def _limits(self, role: str) -> tuple[int, int, float]:
        if role == "responder":
            return (
                self.max_calls, self.max_input_tokens,
                self.max_seconds + self.finishing_seconds,
            )
        if role == "evaluator":
            return (
                self.max_calls - 1,
                self.max_input_tokens - self.finishing_input_reserve // 2,
                self.max_seconds + self.finishing_seconds,
            )
        return (
            self.max_calls - 2,
            self.max_input_tokens - self.finishing_input_reserve,
            self.max_seconds,
        )

    @property
    def research_exhausted(self) -> bool:
        calls, tokens, seconds = self._limits("researcher")
        return (
            self.used_calls >= calls
            or self.used_input_tokens + self._reserved_input >= tokens
            or self._clock() - self._started >= seconds
        )

    async def invoke(self, *, role: str, messages: list[Any], tools=None):
        estimate = message_tokens(messages, tools or ())
        async with self._lock:
            calls, tokens, seconds = self._limits(role)
            remaining = seconds - (self._clock() - self._started)
            if self.used_calls >= calls:
                raise ModelBudgetExceeded("model_calls")
            if self.used_input_tokens + self._reserved_input + estimate > tokens:
                raise ModelBudgetExceeded("input_tokens")
            if remaining <= 0:
                raise ModelBudgetExceeded("elapsed_time")
            self.used_calls += 1
            self._reserved_input += estimate
        charged = estimate
        try:
            async with asyncio.timeout(remaining):
                response = await self.inner.invoke(role=role, messages=messages, tools=tools)
            usage = getattr(response, "usage_metadata", None) or {}
            actual = usage.get("input_tokens")
            if actual is None:
                usage = (
                    (getattr(response, "response_metadata", None) or {}).get("token_usage")
                    or {}
                )
                actual = usage.get("prompt_tokens", usage.get("input_tokens"))
            if isinstance(actual, int) and not isinstance(actual, bool) and actual >= 0:
                charged = actual
            return response
        except TimeoutError as exc:
            raise ModelBudgetExceeded("elapsed_time") from exc
        finally:
            async with self._lock:
                self._reserved_input -= estimate
                self.used_input_tokens += charged
