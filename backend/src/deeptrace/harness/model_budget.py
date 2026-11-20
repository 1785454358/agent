"""Shared admission control for one run, including concurrent research branches."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.domain import ErrorCategory
from deeptrace.harness.model_context import message_tokens, prompt_segment_estimates
from deeptrace.harness.model_gateway import ModelCallError
from deeptrace.observability.model_metrics import ModelMetrics, response_usage


class BudgetStateUnavailable(RuntimeError):
    code = "budget_state_unavailable"
    category = ErrorCategory.FATAL

    def __init__(self):
        super().__init__(self.code)


class ModelBudgetStore(Protocol):
    async def load(self, run_id: str) -> tuple[int, dict[str, Any]] | None: ...

    async def save(
        self, run_id: str, payload: dict[str, Any], expected_revision: int | None
    ) -> int: ...


class ModelBudgetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1] = 1
    started_at: float = Field(ge=0)
    used_calls: int = Field(ge=0)
    charged_input_tokens: int = Field(ge=0)
    max_calls: int = Field(ge=3)
    max_input_tokens: int = Field(gt=0)
    finishing_input_reserve: int = Field(ge=0)
    max_seconds: float = Field(gt=0)
    finishing_seconds: float = Field(gt=0)
    finishing_calls: int = Field(ge=2)
    metrics: ModelMetrics = Field(default_factory=ModelMetrics)
    provider_quota_exhausted: bool = False

    @model_validator(mode="after")
    def consistent_limits(self):
        if (
            self.finishing_calls >= self.max_calls
            or self.finishing_input_reserve >= self.max_input_tokens
            or self.metrics.measured_attempts > self.metrics.attempts
            or self.metrics.attempts != self.used_calls
        ):
            raise ValueError("Invalid model budget snapshot")
        return self


class ModelBudgetExceeded(RuntimeError):
    code = "budget_exhausted"
    category = ErrorCategory.PARTIAL

    def __init__(self, reason: str):
        super().__init__("budget_exhausted:" + reason)


class RunBudgetModelGateway:
    """Reserve before dispatch; charge provider input usage when it is available.

    Missing usage and failed transports retain the estimated input reservation.
    The counters cover gateway dispatches; production uses one provider attempt
    per dispatch. Durable snapshots retain unfinished input estimates after a
    crash and the original wall-clock deadline, including downtime. This is
    admission control, not an exactly-once billing ledger.
    """

    def __init__(
        self,
        inner,
        *,
        max_calls: int = 20,
        max_input_tokens: int = 100_000,
        finishing_input_reserve: int = 20_000,
        max_seconds: float = 600,
        finishing_seconds: float = 120,
        finishing_calls: int = 2,
        monotonic: Callable[[], float] = time.monotonic,
        run_id: str | None = None,
        store: ModelBudgetStore | None = None,
        wall_clock=time.time,
        event_sink=None,
    ):
        if (
            max_calls < 3
            or not 2 <= finishing_calls < max_calls
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
        self.finishing_calls = finishing_calls
        self._clock = monotonic
        self._started = monotonic()
        self._wall_clock = wall_clock
        self._started_at = wall_clock()
        if store is not None and not run_id:
            raise ValueError("Durable model budgets require run_id")
        self.run_id, self._store, self.event_sink = run_id, store, event_sink
        self._loaded = store is None
        self._revision = None
        self._unavailable = False
        self._metrics = ModelMetrics()
        self._lock = asyncio.Lock()
        self.used_calls = 0
        self.used_input_tokens = 0
        self._reserved_input = 0
        self._provider_quota_exhausted = False

    def _elapsed(self):
        return (
            (self._wall_clock() - self._started_at)
            if self._store
            else (self._clock() - self._started)
        )

    @property
    def evaluation_identity(self):
        return getattr(self.inner, "evaluation_identity", None)

    async def _restore(self):
        if self._unavailable:
            raise BudgetStateUnavailable()
        if self._loaded:
            return
        try:
            stored = await self._store.load(self.run_id)
            if stored:
                revision, payload = stored
                state = ModelBudgetSnapshot.model_validate(payload)
                self._revision = revision
                self._started_at = state.started_at
                self.used_calls = state.used_calls
                self.used_input_tokens = state.charged_input_tokens
                self._metrics = state.metrics
                self._provider_quota_exhausted = state.provider_quota_exhausted
                for field in (
                    "max_calls",
                    "max_input_tokens",
                    "finishing_input_reserve",
                    "max_seconds",
                    "finishing_seconds",
                    "finishing_calls",
                ):
                    setattr(self, field, getattr(state, field))
            self._loaded = True
        except Exception as exc:
            self._unavailable = True
            raise BudgetStateUnavailable() from exc

    async def _persist(self):
        if self._store is None:
            return
        state = ModelBudgetSnapshot(
            started_at=self._started_at,
            used_calls=self.used_calls,
            charged_input_tokens=self.used_input_tokens + self._reserved_input,
            max_calls=self.max_calls,
            max_input_tokens=self.max_input_tokens,
            finishing_input_reserve=self.finishing_input_reserve,
            max_seconds=self.max_seconds,
            finishing_seconds=self.finishing_seconds,
            finishing_calls=self.finishing_calls,
            metrics=self._metrics,
            provider_quota_exhausted=self._provider_quota_exhausted,
        )
        try:
            self._revision = await self._store.save(
                self.run_id, state.model_dump(mode="json"), self._revision
            )
        except Exception as exc:
            self._unavailable = True
            raise BudgetStateUnavailable() from exc

    async def admission_limits(self) -> dict[str, int | float]:
        """Read original durable limits without admitting a provider request."""
        async with self._lock:
            await self._restore()
            return {name: getattr(self, name) for name in (
                "max_calls", "max_input_tokens", "max_seconds", "finishing_calls"
            )}

    async def available_input_tokens(self, role: str) -> int:
        """Snapshot usable input after durable usage and concurrent reservations.

        This guides whole-material selection; invoke still performs atomic admission.
        """
        async with self._lock:
            await self._restore()
            return max(0, self._limits(role)[1] - self.used_input_tokens - self._reserved_input)

    def usage_payload(self):
        payload = self._metrics.payload()
        payload["budget_state_available"] = self._loaded and not self._unavailable
        if not payload["budget_state_available"]:
            payload.update(
                usage_complete=False,
                provider_attempts=None,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            )
        return payload

    async def _emit(self, event_type, payload):
        if self.event_sink is None:
            return
        try:
            await self.event_sink.emit(event_type, {"run_id": self.run_id, **payload})
        except Exception as exc:  # noqa: BLE001 - telemetry is a nonfatal boundary
            # Observation failure cannot undo an admitted provider call.
            logging.getLogger(__name__).warning(
                "Model event observer failed: %s", type(exc).__name__
            )

    def _limits(self, role: str) -> tuple[int, int, float]:
        if role == "responder":
            return (
                self.max_calls,
                self.max_input_tokens,
                self.max_seconds + self.finishing_seconds,
            )
        if role == "evaluator":
            return (
                self.max_calls - self.finishing_calls + 1,
                self.max_input_tokens - self.finishing_input_reserve // 2,
                self.max_seconds + self.finishing_seconds,
            )
        return (
            self.max_calls - self.finishing_calls,
            self.max_input_tokens - self.finishing_input_reserve,
            self.max_seconds,
        )

    @property
    def unavailable_reason(self) -> str | None:
        return "model_quota_exhausted" if self._provider_quota_exhausted else None

    @property
    def research_exhausted(self) -> bool:
        calls, tokens, seconds = self._limits("researcher")
        return (
            self._provider_quota_exhausted
            or self.used_calls >= calls
            or self.used_input_tokens + self._reserved_input >= tokens
            or self._elapsed() >= seconds
        )

    async def invoke(self, *, role: str, messages: list[Any], tools=None):
        estimate = message_tokens(messages, tools or ())
        async with self._lock:
            await self._restore()
            if self._provider_quota_exhausted:
                raise ModelCallError(ErrorCategory.FATAL, code="model_quota_exhausted")
            calls, tokens, seconds = self._limits(role)
            remaining = seconds - self._elapsed()
            if remaining <= 0:
                raise ModelBudgetExceeded("elapsed_time")
            if self.used_calls >= calls:
                raise ModelBudgetExceeded("model_calls")
            if self.used_input_tokens + self._reserved_input + estimate > tokens:
                raise ModelBudgetExceeded("input_tokens")
            self.used_calls += 1
            self._reserved_input += estimate
            self._metrics.attempts += 1
            await self._persist()
            call_id = f"{self.run_id or 'run'}:{self.used_calls}"
        charged = estimate
        usage = None
        error_code = None
        started = self._clock()
        segments = prompt_segment_estimates(messages)
        parameters = (self.inner.request_parameters(role)
                      if callable(getattr(self.inner, "request_parameters", None))
                      else self.evaluation_identity)
        await self._emit(
            "model.started",
            {"call_id": call_id, "role": role, "estimated_input_tokens": estimate,
             "prompt_segment_estimates": segments,
             "request_parameters": parameters,
             "prompt_segment_estimates_json": json.dumps(segments, ensure_ascii=False),
             "request_parameters_json": json.dumps(parameters, ensure_ascii=False)},
        )
        try:
            async with asyncio.timeout(remaining):
                response = await self.inner.invoke(
                    role=role, messages=messages, tools=tools
                )
            usage = response_usage(response)
            if usage is not None:
                charged = usage.input_tokens
            return response
        except TimeoutError as exc:
            error_code = "elapsed_time"
            raise ModelBudgetExceeded("elapsed_time") from exc
        except asyncio.CancelledError:
            error_code = "cancelled"
            raise
        except ModelCallError as exc:
            error_code = exc.code
            if exc.code == "model_quota_exhausted":
                self._provider_quota_exhausted = True
            raise
        except Exception:
            error_code = "model_error"
            raise
        finally:
            elapsed = max(0, self._clock() - started)
            async with self._lock:
                self._reserved_input -= estimate
                self.used_input_tokens += charged
                self._metrics.record(role, usage, elapsed)
                await self._persist()
            await self._emit(
                "model.failed" if error_code else "model.completed",
                {
                    "call_id": call_id,
                    "role": role,
                    "duration_ms": round(elapsed * 1000),
                    "error_code": error_code,
                    "usage_known": usage is not None,
                    "input_tokens": usage.input_tokens if usage else None,
                    "output_tokens": usage.output_tokens if usage else None,
                },
            )
