"""Ports shared by semantic long-term-memory adapters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from deeptrace.domain import MemoryRecord


class EmbeddingGateway(Protocol):
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class MemoryVectorHit:
    memory_id: str
    distance: float


class MemoryVectorIndex(Protocol):
    async def records_requiring_index(
        self, records: Sequence[MemoryRecord]
    ) -> list[MemoryRecord]: ...

    async def upsert(
        self,
        records: Sequence[MemoryRecord],
        embeddings: Sequence[Sequence[float]],
    ) -> None: ...

    async def query(
        self,
        *,
        query_embedding: Sequence[float],
        candidate_ids: Sequence[str],
        limit: int,
    ) -> list[MemoryVectorHit]: ...

    async def delete(self, memory_ids: Sequence[str]) -> None: ...
