"""Semantic long-term-memory orchestration with deterministic fallback."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from deeptrace.domain import MemoryRecord, MemoryType
from deeptrace.domain.memory import MemoryNamespace
from deeptrace.harness.memory.recall import select_memories
from deeptrace.harness.memory.vector_index import EmbeddingGateway, MemoryVectorIndex


class SemanticMemoryRetriever:
    """Coordinate authoritative records, embeddings and the Chroma index."""

    def __init__(
        self,
        store,
        embeddings: EmbeddingGateway,
        index: MemoryVectorIndex,
    ) -> None:
        self._store = store
        self._embeddings = embeddings
        self._index = index

    async def index(self, records: Sequence[MemoryRecord]) -> None:
        pending = await self._index.records_requiring_index(records)
        if not pending:
            return
        vectors = await self._embeddings.embed_documents(
            [record.content for record in pending]
        )
        await self._index.upsert(pending, vectors)

    async def recall(
        self,
        *,
        namespaces: list[MemoryNamespace],
        memory_types: set[MemoryType],
        query: str,
        now: datetime,
        limit: int,
    ) -> list[MemoryRecord]:
        candidates = await self._store.list_eligible(
            namespaces=namespaces,
            memory_types=memory_types,
            now=now,
        )
        if not candidates or limit <= 0:
            return []
        try:
            await self.index(candidates)
            query_embedding = await self._embeddings.embed_query(query)
            hits = await self._index.query(
                query_embedding=query_embedding,
                candidate_ids=[record.id for record in candidates],
                limit=min(len(candidates), max(limit * 3, limit)),
            )
            records = await self._store.get_many_by_ids(
                [hit.memory_id for hit in hits]
            )
            distances = {hit.memory_id: hit.distance for hit in hits}
            records.sort(
                key=lambda record: (
                    -self._score(record, distances[record.id], now),
                    record.identity(),
                )
            )
            return records[:limit]
        except Exception:
            logging.getLogger(__name__).exception(
                "semantic memory recall failed; using deterministic ranking"
            )
            return select_memories(candidates, query=query, now=now, limit=limit)

    @staticmethod
    def _score(record: MemoryRecord, distance: float, now: datetime) -> float:
        similarity = max(0.0, min(1.0, 1.0 - distance))
        age_days = max(0.0, (now - record.updated_at).total_seconds() / 86_400)
        recency = 1.0 / (1.0 + age_days)
        return (
            similarity * 0.70
            + record.importance * 0.15
            + record.confidence * 0.10
            + recency * 0.05
        )
