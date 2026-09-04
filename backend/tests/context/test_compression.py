from datetime import UTC, date, datetime

import numpy as np
import pytest

from deeptrace.context import (
    ChunkSelection,
    CompressionRequest,
    CompressionService,
    build_extractive_note,
)
from deeptrace.context.compression import _split_sentences, extract_event_dates
from deeptrace.models import (
    DocumentChunk,
    RawDocument,
    ResearchTimeRange,
    ScraperUsed,
)


class FakeEmbeddingRuntime:
    """词表指示向量：命中关键词的文本彼此相似，足以驱动打分逻辑。"""

    def __init__(self, vocabulary: list[str]) -> None:
        self._vocabulary = vocabulary
        self._index = {word: position for position, word in enumerate(vocabulary)}

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(len(self._vocabulary), dtype=np.float32)
        for word, position in self._index.items():
            if word in text:
                vector[position] = 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, len(self._vocabulary)), dtype=np.float32)
        return np.stack([self._vector(item) for item in texts])

    def query_vector(self, query: str) -> np.ndarray:
        return self._vector(query)


def _document(
    doc_id: str,
    title: str,
    content: str,
    published_at: datetime | None = None,
) -> RawDocument:
    return RawDocument(
        doc_id=doc_id,
        requested_url=f"https://example.com/{doc_id}",
        final_url=f"https://example.com/{doc_id}",
        canonical_url=None,
        title=title,
        content=content,
        content_hash="hash",
        fetched_at=datetime(2024, 12, 1, tzinfo=UTC),
        source_published_at=published_at,
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )


def _chunk(doc_id: str, index: int, text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"{doc_id}:{index}",
        doc_id=doc_id,
        index=index,
        text=text,
        token_count=32,
        char_start=0,
        char_end=len(text),
    )


def _selection(chunks, is_relevant=True, top1=0.82) -> ChunkSelection:
    return ChunkSelection(
        chunks=chunks,
        is_relevant=is_relevant,
        top1_user_score=0.51,
        top1_active_score=top1,
        top1_fused_score=top1,
    )


def _request(
    document: RawDocument,
    selection: ChunkSelection,
    *,
    user_query: str = "AI Agent 年度进展",
    active_query: str = "Agent 框架与工具调用",
    order: int = 0,
    time_range: ResearchTimeRange | None = None,
) -> CompressionRequest:
    return CompressionRequest(
        tool_call_id=f"call-{order}",
        order=order,
        document=document,
        selection=selection,
        user_query=user_query,
        active_query=active_query,
        task_id="task-01",
        section_id="section-01",
        time_range=time_range,
    )


CONTENT = (
    "2024年3月15日，某团队发布了全新的 Agent 框架并开放工具调用接口。"
    "该框架支持多智能体协同与长上下文记忆管理。"
    "2024年11月，该框架完成了第二次大版本迭代。"
    "开发者社区在发布当周就贡献了上百个插件。"
    "今天天气很好，适合出门散步。"
)
TIME_RANGE_2024 = ResearchTimeRange(
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
    description="2024 年",
)


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


def test_compress_filters_sentences_by_similarity_with_zero_usage() -> None:
    runtime = FakeEmbeddingRuntime(["agent", "框架", "工具", "插件", "天气"])
    document = _document("doc-1", "Agent 年度盘点", CONTENT)
    chunks = [
        _chunk("doc-1", 0, CONTENT[:60]),
        _chunk("doc-1", 1, CONTENT[60:]),
    ]
    service = CompressionService(runtime)

    outcome = _run(service.compress_one(_request(document, _selection(chunks))))

    assert outcome.error is None
    assert outcome.usage.input_tokens == 0
    assert outcome.usage.output_tokens == 0
    assert outcome.usage.total_tokens == 0
    note = outcome.note
    assert note is not None
    assert note.compression_status == "compressed"
    assert note.key_points
    assert set(note.key_points) <= set(note.evidence_snippets)
    # 只保留原句，全部能在原文中精确定位，且不含无关句子。
    for snippet in note.evidence_snippets:
        assert snippet in document.content
    assert all("天气" not in snippet for snippet in note.evidence_snippets)
    # 恢复阅读顺序。
    positions = [document.content.index(item) for item in note.evidence_snippets]
    assert positions == sorted(positions)
    assert note.relevance_score == pytest.approx(0.82)


def test_irrelevant_selection_returns_empty_note_without_model_call() -> None:
    runtime = FakeEmbeddingRuntime(["agent"])
    service = CompressionService(runtime)

    outcome = _run(
        service.compress_one(
            _request(_document("doc-1", "标题", CONTENT), _selection([], False))
        )
    )

    assert outcome.usage.total_tokens == 0
    assert outcome.note is not None
    assert outcome.note.compression_status == "irrelevant"
    assert outcome.note.key_points == []


def test_no_sentence_passing_threshold_keeps_best_sentence() -> None:
    runtime = FakeEmbeddingRuntime(["量子", "纠缠"])
    document = _document(
        "doc-1", "物理快讯", "量子纠缠实验取得新进展。完全无关的查询词。"
    )
    service = CompressionService(runtime, sentence_threshold=0.99)

    outcome = _run(
        service.compress_one(
            _request(
                document,
                _selection([_chunk("doc-1", 0, document.content)]),
            )
        )
    )

    note = outcome.note
    assert note is not None
    assert note.compression_status == "compressed"
    assert len(note.evidence_snippets) == 1
    assert note.evidence_snippets[0] in document.content


def test_overlapping_chunks_do_not_duplicate_sentences() -> None:
    runtime = FakeEmbeddingRuntime(["agent", "框架", "工具", "插件"])
    document = _document("doc-1", "标题", CONTENT)
    chunks = [
        _chunk("doc-1", 0, CONTENT[:80]),
        _chunk("doc-1", 1, CONTENT[60:]),
    ]
    service = CompressionService(runtime)

    outcome = _run(service.compress_one(_request(document, _selection(chunks))))

    note = outcome.note
    assert note is not None
    assert len(note.evidence_snippets) == len(set(note.evidence_snippets))


def test_event_dates_extracted_from_sentences_drive_temporal_relation() -> None:
    assert extract_event_dates("2024年3月15日发布。") == (
        date(2024, 3, 15),
        date(2024, 3, 15),
    )
    assert extract_event_dates("2024年10月更新。") == (
        date(2024, 10, 1),
        date(2024, 10, 31),
    )
    assert extract_event_dates("回顾 2024 年全年。") == (
        date(2024, 1, 1),
        date(2024, 12, 31),
    )
    assert extract_event_dates("October 23, 2024 发布。") == (
        date(2024, 10, 23),
        date(2024, 10, 23),
    )
    assert extract_event_dates("没有任何日期。") == (None, None)

    runtime = FakeEmbeddingRuntime(["agent", "框架", "工具", "插件"])
    service = CompressionService(runtime)
    chunks = [_chunk("doc-1", 0, CONTENT)]

    in_range = _run(
        service.compress_one(
            _request(
                _document("doc-1", "标题", CONTENT),
                _selection(chunks),
                time_range=TIME_RANGE_2024,
            )
        )
    )
    assert in_range.note is not None
    assert in_range.note.event_start_date == date(2024, 3, 15)
    assert in_range.note.event_end_date == date(2024, 11, 30)
    assert in_range.note.temporal_relation == "in_range"

    retrospective = _run(
        service.compress_one(
            _request(
                _document(
                    "doc-2",
                    "标题",
                    CONTENT,
                    published_at=datetime(2025, 2, 1, tzinfo=UTC),
                ),
                _selection([_chunk("doc-2", 0, CONTENT)]),
                time_range=TIME_RANGE_2024,
            )
        )
    )
    assert retrospective.note is not None
    assert retrospective.note.temporal_relation == "retrospective"


def test_compress_many_restores_call_order() -> None:
    runtime = FakeEmbeddingRuntime(["agent", "框架"])
    service = CompressionService(runtime)
    document = _document("doc-1", "标题", CONTENT)
    requests = [
        _request(document, _selection([_chunk("doc-1", 0, CONTENT)]), order=1),
        _request(document, _selection([_chunk("doc-1", 0, CONTENT)]), order=0),
    ]

    outcomes = _run(service.compress_many(requests))

    assert [item.order for item in outcomes] == [0, 1]


def test_split_sentences_keeps_long_text_verbatim_and_bounded() -> None:
    long_text = "这是一个非常长的句子，" * 40
    pieces = _split_sentences(long_text)
    assert all(len(piece) <= 220 for piece in pieces)
    assert "".join(pieces) == long_text
    assert _split_sentences("第一句。第二句！第三句") == [
        "第一句。",
        "第二句！",
        "第三句",
    ]


def test_extractive_note_preserves_task_identity(raw_document) -> None:
    selection = ChunkSelection(
        chunks=[],
        is_relevant=False,
        top1_user_score=0.1,
        top1_active_score=0.2,
        top1_fused_score=0.2,
    )

    note = build_extractive_note(
        raw_document,
        selection,
        "当前查询",
        "task-01",
        "section-01",
        "失败",
    )

    assert note.task_id == "task-01"
    assert note.section_id == "section-01"
