from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ModelGateway(Protocol):
    async def invoke(self, *, role: str, messages: list[Any]) -> Any: ...


class ToolGateway(Protocol):
    async def execute(self, request: Any) -> Any: ...


class EvidenceStore(Protocol):
    async def get_many(self, evidence_ids: list[str]) -> list[Any]: ...


class EventSink(Protocol):
    async def emit(self, event_type: str, payload: dict[str, Any]) -> None: ...


class Clock(Protocol):
    def now(self) -> Any: ...


@dataclass(frozen=True)
class HarnessContext:
    user_id: str
    workspace_id: str
    model_gateway: ModelGateway
    tool_gateway: ToolGateway
    evidence_store: EvidenceStore
    event_sink: EventSink
    clock: Clock
