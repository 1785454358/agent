"""Real model gateway over LangChain chat models."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import SystemMessage

from deeptrace.domain import ErrorCategory


class ModelCallError(RuntimeError):
    def __init__(self, category: ErrorCategory):
        super().__init__("model_request_failed")
        self.category = category


def _transient(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return (
        isinstance(exc, (TimeoutError, ConnectionError))
        or status in {408, 429, 500, 502, 503, 504}
        or type(exc).__name__
        in {"APITimeoutError", "APIConnectionError", "ConnectError", "ReadTimeout"}
    )


def _validate_context_envelope(messages: list[Any]) -> None:
    has_instruction = any(
        isinstance(message, SystemMessage) and str(message.content).strip()
        for message in messages
    )
    content = "\n".join(str(getattr(message, "content", "")) for message in messages)
    if (
        not has_instruction
        or "原始任务：" not in content
        or "当前约束：" not in content
    ):
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
    ) -> None:
        self._model = model
        self._role_overrides = role_overrides or {}
        if retry_attempts < 1 or retry_base_seconds < 0 or timeout_seconds <= 0:
            raise ValueError("Invalid model transport limits")
        self._attempts = retry_attempts
        self._delay = retry_base_seconds
        self._timeout = timeout_seconds

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
                async with asyncio.timeout(self._timeout):
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
                    ErrorCategory.TRANSIENT if transient else ErrorCategory.FATAL
                ) from exc
