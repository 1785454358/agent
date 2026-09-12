from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from deeptrace.domain import Evidence, ToolRequest, ToolResult
from deeptrace.tools.evidence_store import EvidenceDraft
from deeptrace.tools.policy import ToolCaller, UrlAuthorization


class ModelGateway(Protocol):
    async def invoke(self, *, role: str, messages: list[Any]) -> Any: ...


class ToolGateway(Protocol):
    async def execute(
        self,
        *,
        tenant_id: str,
        caller: ToolCaller,
        request: ToolRequest,
        authorization: UrlAuthorization | None = None,
        provider_id: str = "default",
        refresh: bool = False,
    ) -> ToolResult: ...


class EvidenceStore(Protocol):
    async def ingest(self, tenant_id: str, draft: EvidenceDraft) -> Evidence: ...

    async def get_many(
        self, tenant_id: str, evidence_ids: Sequence[str]
    ) -> tuple[Evidence, ...]: ...

    async def read_body(self, tenant_id: str, evidence_id: str) -> str: ...


class EventSink(Protocol):
    async def emit(self, event_type: str, payload: dict[str, Any]) -> None: ...


class Clock(Protocol):
    def now(self) -> Any: ...


class MemoryStorePort(Protocol):
    """Long-term memory port; implementations wrap a LangGraph Store."""

    async def put(self, record: Any) -> Any: ...

    async def get(self, namespace: Any, identity: str) -> Any | None: ...

    async def list_namespace(
        self, namespace: Any, *, include_inactive: bool = False
    ) -> list[Any]: ...


@dataclass(frozen=True)
class HarnessContext:
    user_id: str
    workspace_id: str
    model_gateway: ModelGateway
    tool_gateway: ToolGateway
    evidence_store: EvidenceStore
    event_sink: EventSink
    clock: Clock
    memory_store: MemoryStorePort | None = None
