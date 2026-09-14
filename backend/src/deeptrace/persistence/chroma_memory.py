"""Chroma adapter for the non-authoritative long-term-memory vector index."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from typing import Any

from deeptrace.domain import MemoryRecord
from deeptrace.harness.memory.vector_index import MemoryVectorHit


def _content_hash(record: MemoryRecord) -> str:
    return hashlib.sha256(record.content.encode("utf-8")).hexdigest()


class ChromaMemoryVectorIndex:
    """Store search vectors while keeping MySQL as the source of truth."""

    def __init__(self, client: Any, collection_name: str) -> None:
        self._collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def records_requiring_index(
        self, records: Sequence[MemoryRecord]
    ) -> list[MemoryRecord]:
        values = list(records)
        if not values:
            return []

        def _get() -> dict[str, Any]:
            return self._collection.get(
                ids=[record.id for record in values],
                include=["metadatas"],
            )

        result = await asyncio.to_thread(_get)
        indexed = {
            memory_id: metadata or {}
            for memory_id, metadata in zip(
                result.get("ids", []), result.get("metadatas", [])
            )
        }
        return [
            record
            for record in values
            if indexed.get(record.id, {}).get("content_hash") != _content_hash(record)
        ]

    async def upsert(
        self,
        records: Sequence[MemoryRecord],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        values = list(records)
        vectors = [list(vector) for vector in embeddings]
        if not values:
            return
        if len(values) != len(vectors):
            raise ValueError("records and embeddings must have the same length")
        metadatas = []
        for record in values:
            scope, owner, kind = record.namespace
            metadatas.append(
                {
                    "memory_id": record.id,
                    "namespace_scope": scope,
                    "namespace_owner": owner,
                    "namespace_kind": kind,
                    "memory_type": record.type.value,
                    "status": record.status.value,
                    "content_hash": _content_hash(record),
                }
            )
        await asyncio.to_thread(
            self._collection.upsert,
            ids=[record.id for record in values],
            documents=[record.content for record in values],
            embeddings=vectors,
            metadatas=metadatas,
        )

    async def query(
        self,
        *,
        query_embedding: Sequence[float],
        candidate_ids: Sequence[str],
        limit: int,
    ) -> list[MemoryVectorHit]:
        ids = list(dict.fromkeys(candidate_ids))
        if not ids or limit <= 0:
            return []
        result = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[list(query_embedding)],
            ids=ids,
            n_results=min(limit, len(ids)),
            include=["distances"],
        )
        result_ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            MemoryVectorHit(memory_id=memory_id, distance=float(distance))
            for memory_id, distance in zip(result_ids, distances)
        ]

    async def delete(self, memory_ids: Sequence[str]) -> None:
        ids = list(dict.fromkeys(memory_ids))
        if ids:
            await asyncio.to_thread(self._collection.delete, ids=ids)
