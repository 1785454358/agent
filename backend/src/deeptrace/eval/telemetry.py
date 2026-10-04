"""Eval-only pre-request ceilings and honest provider usage accounting."""

from __future__ import annotations

import asyncio
import copy
from contextlib import ExitStack
from threading import Lock

from deeptrace.domain.execution import RequestBudgetExceeded


class RequestLimitReached(RequestBudgetExceeded):
    def __init__(self):
        super().__init__("evaluation_request_limit")


class RequestCounter:
    def __init__(self, limit: int, *, used: int = 0):
        if (
            type(limit) is not int
            or limit < 1
            or type(used) is not int
            or used < 0
            or used > limit
        ):
            raise ValueError(
                "positive request ceiling and valid consumed count required"
            )
        self.limit = limit
        self.used = used
        self._lock = Lock()

    def reserve(self, *other_counters: RequestCounter) -> None:
        counters = sorted({self, *other_counters}, key=id)
        with ExitStack() as stack:
            for counter in counters:
                stack.enter_context(counter._lock)
            if any(counter.used >= counter.limit for counter in counters):
                raise RequestLimitReached
            for counter in counters:
                counter.used += 1


def _usage(response) -> dict | None:
    metadata = getattr(response, "usage_metadata", None)
    if not isinstance(metadata, dict):
        return None
    if any(
        type(metadata.get(key)) is not int or metadata[key] < 0
        for key in ("input_tokens", "output_tokens")
    ):
        return None
    return {key: metadata[key] for key in ("input_tokens", "output_tokens")}


class ModelTelemetry:
    def __init__(self, *, provider_instrumented: bool = True):
        self.provider_instrumented = provider_instrumented
        self._attempts: list[dict] = []

    def start(self) -> int:
        self._attempts.append({"status": "pending", "usage": None, "error_type": None})
        return len(self._attempts) - 1

    def finish(self, index: int, response=None, *, error=None) -> None:
        self._attempts[index] = {
            "status": "cancelled"
            if isinstance(error, asyncio.CancelledError)
            else ("error" if error else "ok"),
            "usage": _usage(response) if error is None else None,
            "error_type": type(error).__name__ if error else None,
        }

    def snapshot(self) -> dict:
        measured = [a["usage"] for a in self._attempts if a["usage"] is not None]
        missing = len(self._attempts) - len(measured)
        observed = {
            key: sum(u[key] for u in measured)
            for key in ("input_tokens", "output_tokens")
        }
        return {
            "provider_attempts": len(self._attempts)
            if self.provider_instrumented
            else None,
            "usage_observation_level": "provider_attempt"
            if self.provider_instrumented
            else "gateway_response",
            "measured_usage_attempts": len(measured),
            "missing_usage_attempts": missing,
            "observed_input_tokens": observed["input_tokens"],
            "observed_output_tokens": observed["output_tokens"],
            "input_tokens": None if missing else observed["input_tokens"],
            "output_tokens": None if missing else observed["output_tokens"],
            "cost": None,
            "attempts": copy.deepcopy(self._attempts),
        }


class MeteredChatModel:
    """Wrap each SDK-facing ainvoke, including gateway-managed retries.

    SDK internal retries must be disabled by the model factory. Bound models
    share both counters and telemetry. An attempt can fail before HTTP dispatch;
    accounting conservatively retains it rather than guessing that it was free.
    """

    def __init__(
        self,
        inner,
        telemetry: ModelTelemetry,
        run_counter: RequestCounter,
        batch_counter: RequestCounter,
    ):
        self._inner = inner
        self.telemetry = telemetry
        self._run_counter = run_counter
        self._batch_counter = batch_counter

    def bind_tools(self, tools):
        return type(self)(
            self._inner.bind_tools(tools),
            self.telemetry,
            self._run_counter,
            self._batch_counter,
        )

    def bind(self, **kwargs):
        return type(self)(
            self._inner.bind(**kwargs),
            self.telemetry,
            self._run_counter,
            self._batch_counter,
        )

    async def ainvoke(self, *args, **kwargs):
        self._run_counter.reserve(self._batch_counter)
        index = self.telemetry.start()
        try:
            response = await self._inner.ainvoke(*args, **kwargs)
        except BaseException as exc:
            self.telemetry.finish(index, error=exc)
            raise
        self.telemetry.finish(index, response)
        return response
