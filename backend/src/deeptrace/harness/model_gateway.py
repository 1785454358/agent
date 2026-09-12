"""Real model gateway over LangChain chat models."""

from __future__ import annotations

from typing import Any


class ChatModelGateway:
    """ModelGateway implementation backed by a LangChain chat model.

    Role selects per-role binding overrides; the raw message is returned and
    strategy nodes extract text deterministically.
    """

    def __init__(
        self,
        model: Any,
        *,
        role_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._model = model
        self._role_overrides = role_overrides or {}

    async def invoke(self, *, role: str, messages: list[Any]) -> Any:
        overrides = self._role_overrides.get(role)
        if not overrides:
            return await self._model.ainvoke(messages)
        return await self._model.bind(**overrides).ainvoke(messages)
