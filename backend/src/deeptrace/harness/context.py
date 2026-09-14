from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from deeptrace.domain import Evidence, MemoryRecord, MemoryType, ToolRequest, ToolResult
from deeptrace.domain.memory import MemoryNamespace
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

    async def put(self, record: MemoryRecord) -> MemoryRecord: ...

    async def get(
        self, namespace: MemoryNamespace, identity: str
    ) -> MemoryRecord | None: ...

    async def list_namespace(
        self, namespace: MemoryNamespace, *, include_inactive: bool = False
    ) -> list[MemoryRecord]: ...

    async def list_eligible(
        self,
        *,
        namespaces: list[MemoryNamespace],
        memory_types: set[MemoryType],
        now: Any,
    ) -> list[MemoryRecord]: ...

    async def get_many_by_ids(
        self, memory_ids: list[str]
    ) -> list[MemoryRecord]: ...


class MemoryRetrieverPort(Protocol):
    async def recall(
        self,
        *,
        namespaces: list[MemoryNamespace],
        memory_types: set[MemoryType],
        query: str,
        now: Any,
        limit: int,
    ) -> list[MemoryRecord]: ...

    async def index(self, records: Sequence[MemoryRecord]) -> None: ...


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
    memory_retriever: MemoryRetrieverPort | None = None
    memory_recall_limit: int = 5
