from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deeptrace.domain import MemoryRecord, MemoryType
from deeptrace.harness.memory.retriever import SemanticMemoryRetriever
from deeptrace.harness.memory.vector_index import MemoryVectorHit

NOW = datetime(2026, 9, 14, tzinfo=UTC)


def _record(
    subject: str,
    content: str,
    *,
    importance: float = 0.5,
    confidence: float = 0.8,
    updated_at: datetime = NOW,
) -> MemoryRecord:
    return MemoryRecord(
        type=MemoryType.FACT,
        namespace=("workspace", "ws-1", "facts"),
        subject=subject,
        content=content,
        source_evidence_ids=["evidence-1"],
        importance=importance,
        confidence=confidence,
        created_at=NOW,
        updated_at=updated_at,
    )


class _Store:
    def __init__(self, records: list[MemoryRecord], trace: list[str]) -> None:
        self.records = records
        self.trace = trace

    async def list_eligible(self, **kwargs):
        self.trace.append("mysql_filter")
        return self.records

    async def get_many_by_ids(self, memory_ids):
        self.trace.append("mysql_refetch")
        by_id = {record.id: record for record in self.records}
        return [by_id[memory_id] for memory_id in memory_ids if memory_id in by_id]


class _Embeddings:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    async def embed_documents(self, texts):
        self.trace.append("embed_documents")
        return [[1.0, 0.0] for _ in texts]

    async def embed_query(self, text):
        self.trace.append("embed_query")
        return [1.0, 0.0]


class _Index:
    def __init__(
        self,
        hits: list[MemoryVectorHit],
        trace: list[str],
        *,
        fail: bool = False,
    ) -> None:
        self.hits = hits
        self.trace = trace
        self.fail = fail

    async def records_requiring_index(self, records):
        self.trace.append("chroma_check")
        return records[:1]

    async def upsert(self, records, embeddings):
        self.trace.append("chroma_upsert")

    async def query(self, **kwargs):
        self.trace.append("chroma_query")
        if self.fail:
            raise RuntimeError("chroma unavailable")
        return self.hits

    async def delete(self, memory_ids):
        return None


@pytest.mark.asyncio
async def test_recall_filters_then_queries_chroma_then_refetches_mysql() -> None:
    trace: list[str] = []
    low = _record("low", "checkpoint recovery", importance=0.1, confidence=0.5)
    high = _record("high", "checkpoint resume", importance=1.0, confidence=1.0)
    index = _Index(
        [
            MemoryVectorHit(memory_id=low.id, distance=0.10),
            MemoryVectorHit(memory_id=high.id, distance=0.11),
        ],
        trace,
    )
    retriever = SemanticMemoryRetriever(
        _Store([low, high], trace), _Embeddings(trace), index
    )

    result = await retriever.recall(
        namespaces=[("workspace", "ws-1", "facts")],
        memory_types={MemoryType.FACT},
        query="checkpoint recovery",
        now=NOW,
        limit=2,
    )

    assert trace == [
        "mysql_filter",
        "chroma_check",
        "embed_documents",
        "chroma_upsert",
        "embed_query",
        "chroma_query",
        "mysql_refetch",
    ]
    assert [record.id for record in result] == [high.id, low.id]


@pytest.mark.asyncio
async def test_recall_falls_back_to_deterministic_ranking_when_chroma_fails() -> None:
    trace: list[str] = []
    wanted = _record("checkpoint", "checkpoint recovery in MySQL")
    unrelated = _record(
        "weather", "weather forecast", updated_at=NOW - timedelta(days=1)
    )
    retriever = SemanticMemoryRetriever(
        _Store([unrelated, wanted], trace),
        _Embeddings(trace),
        _Index([], trace, fail=True),
    )

    result = await retriever.recall(
        namespaces=[("workspace", "ws-1", "facts")],
        memory_types={MemoryType.FACT},
        query="checkpoint recovery",
        now=NOW,
        limit=2,
    )

    assert [record.id for record in result] == [wanted.id]
    assert "mysql_refetch" not in trace
