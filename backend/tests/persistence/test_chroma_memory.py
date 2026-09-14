from __future__ import annotations

from datetime import UTC, datetime

import chromadb
import pytest

from deeptrace.domain import MemoryRecord, MemoryType
from deeptrace.persistence.chroma_memory import ChromaMemoryVectorIndex

NOW = datetime(2026, 9, 14, tzinfo=UTC)


def _record(subject: str, content: str) -> MemoryRecord:
    return MemoryRecord(
        type=MemoryType.FACT,
        namespace=("workspace", "ws-1", "facts"),
        subject=subject,
        content=content,
        source_evidence_ids=["evidence-1"],
        confidence=0.9,
        importance=0.8,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_chroma_index_tracks_content_hash_and_updates_changed_records() -> None:
    index = ChromaMemoryVectorIndex(chromadb.Client(), "test-memory-hash")
    first = _record("checkpoint", "checkpoint 使用 MySQL")

    assert await index.records_requiring_index([first]) == [first]
    await index.upsert([first], [[1.0, 0.0]])
    assert await index.records_requiring_index([first]) == []

    changed = first.model_copy(update={"content": "checkpoint 支持恢复"})
    assert await index.records_requiring_index([changed]) == [changed]
    await index.upsert([changed], [[0.0, 1.0]])
    assert await index.records_requiring_index([changed]) == []


@pytest.mark.asyncio
async def test_chroma_query_is_restricted_to_mysql_candidate_ids() -> None:
    index = ChromaMemoryVectorIndex(chromadb.Client(), "test-memory-filter")
    allowed = _record("allowed", "允许召回")
    blocked = _record("blocked", "其他作用域")
    await index.upsert([allowed, blocked], [[1.0, 0.0], [1.0, 0.0]])

    hits = await index.query(
        query_embedding=[1.0, 0.0],
        candidate_ids=[allowed.id],
        limit=5,
    )

    assert [(hit.memory_id, hit.distance) for hit in hits] == [(allowed.id, 0.0)]
    assert await index.query(
        query_embedding=[1.0, 0.0], candidate_ids=[], limit=5
    ) == []
