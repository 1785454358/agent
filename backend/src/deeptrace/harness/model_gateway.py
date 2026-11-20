"""Real model gateway over LangChain chat models."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from deeptrace.domain import ErrorCategory
from deeptrace.harness.model_context import TaskContext


class ModelCallError(RuntimeError):
    def __init__(self, category: ErrorCategory, *, code: str = "model_request_failed"):
        super().__init__(code)
        self.category = category
        self.code = code


def _quota_exhausted(exc: Exception) -> bool:
    body = getattr(exc, "body", None)
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        body = body["error"]
    codes = [getattr(exc, "code", None)]
    if isinstance(body, dict):
        codes.extend([body.get("code"), body.get("type")])
    return any(code in ("credit_quota_exceeded", "insufficient_quota", "quota_exceeded") for code in codes)


def _transient(exc: Exception) -> bool:
    if _quota_exhausted(exc):
        return False
    status = getattr(exc, "status_code", None)
    return (
        isinstance(exc, (TimeoutError, ConnectionError))
        or status in {408, 429, 500, 502, 503, 504}
        or type(exc).__name__
        in {
            "APITimeoutError",
            "APIConnectionError",
            "OpenAIConnectionError",
            "OpenAITimeoutError",
            "ConnectError",
            "ReadTimeout",
        }
    )


def _validate_context_envelope(messages: list[Any]) -> None:
    has_instruction = any(
        isinstance(message, SystemMessage) and str(message.content).strip()
        for message in messages
    )
    has_task = False
    for message in messages:
        if not isinstance(message, HumanMessage):
            continue
        try:
            task = TaskContext.model_validate(message.additional_kwargs.get('task_context'))
            has_task = bool(task.task.strip())
        except ValidationError:
            continue
        if has_task:
            break
    if not has_instruction or not has_task:
        raise ValueError(
            "model_context_invariant: system instruction, original task, "
            "and current constraints are required"
        )


class ChatModelGateway:
    """ModelGateway implementation backed by a LangChain chat model.

    Role selects per-role binding overrides; the raw message is returned and
    strategy nodes extract text deterministically. When ``tools`` is provided
    the model is bound for tool calling (used by the agent executor loop).
    """

    def __init__(
        self,
        model: Any,
        *,
        role_overrides: dict[str, dict[str, Any]] | None = None,
        retry_attempts: int = 2,
        retry_base_seconds: float = 0.5,
        timeout_seconds: float = 60,
        role_timeout_seconds: dict[str, float] | None = None,
    ) -> None:
        self._model = model
        self._role_overrides = role_overrides or {}
        if retry_attempts < 1 or retry_base_seconds < 0 or timeout_seconds <= 0:
            raise ValueError("Invalid model transport limits")
        self._attempts = retry_attempts
        self._delay = retry_base_seconds
        self._timeout = timeout_seconds
        self._role_timeouts = dict(role_timeout_seconds or {})
        if any(seconds <= 0 for seconds in self._role_timeouts.values()):
            raise ValueError("Invalid role timeout")

    @property
    def evaluation_identity(self):
        return self.request_parameters("evaluator") if getattr(self._model, "model_name", None) else None

    def request_parameters(self, role):
        # Explicit safe request fields only: never serialize credentials or
        # client objects into persisted checkpoints or telemetry.
        return {"gateway": type(self).__name__,
                "model": getattr(self._model, "model_name", None),
                "base_url": str(getattr(self._model, "openai_api_base", "")),
                "temperature": getattr(self._model, "temperature", None),
                "max_tokens": getattr(self._model, "max_tokens", None),
                "extra_body": getattr(self._model, "extra_body", None),
                "top_p": getattr(self._model, "top_p", None),
                "seed": getattr(self._model, "seed", None),
                "reasoning_effort": getattr(self._model, "reasoning_effort", None),
                "model_kwargs": {key: value for key, value in getattr(self._model, "model_kwargs", {}).items()
                                 if key in {"temperature", "top_p", "max_tokens", "max_completion_tokens", "seed", "reasoning_effort", "response_format", "extra_body"}},
                "role": {key: value for key, value in self._role_overrides.get(role, {}).items()
                         if key in {"temperature", "top_p", "max_tokens", "max_completion_tokens", "seed", "reasoning_effort", "response_format", "extra_body"}}}

    async def invoke(
        self,
        *,
        role: str,
        messages: list[Any],
        tools: Sequence[Any] | None = None,
    ) -> Any:
        _validate_context_envelope(messages)
        runnable = self._model
        overrides = self._role_overrides.get(role)
        if tools:
            runnable = runnable.bind_tools(list(tools))
        if overrides:
            runnable = runnable.bind(**overrides)
        for attempt in range(self._attempts):
            try:
                async with asyncio.timeout(self._role_timeouts.get(role, self._timeout)):
                    return await runnable.ainvoke(messages)
            except Exception as exc:
                transient = _transient(exc)
                if transient and attempt + 1 < self._attempts:
                    await asyncio.sleep(min(self._delay * 2**attempt, 10))
                    continue
                logging.getLogger(__name__).exception(
                    "Model call failed for role %s", role
                )
                raise ModelCallError(
                    ErrorCategory.TRANSIENT if transient else ErrorCategory.FATAL,
                    code="model_quota_exhausted" if _quota_exhausted(exc) else "model_request_failed",
                ) from exc
