from datetime import datetime, timezone

import pytest

from deeptrace.context import (
    ChunkSelection,
    ResearchNotePayload,
    build_extractive_note,
    parse_note_json,
)
from deeptrace.models import DocumentChunk, RawDocument, ScraperUsed


def test_note_json_is_repaired_and_invalid_output_has_extractive_fallback() -> None:
    """防止轻微 JSON 错误丢失结构，或最终失败时整页信息白抓。"""
    repaired = parse_note_json(
        "{'title':'Agent 招聘','key_points':['掌握 LangGraph'],"
        "'evidence_snippets':['熟悉工具调用'],}"
    )
    assert repaired == ResearchNotePayload(
        title="Agent 招聘",
        key_points=["掌握 LangGraph"],
        evidence_snippets=["熟悉工具调用"],
    )

    with pytest.raises(ValueError):
        parse_note_json("这不是 JSON，也没有结构化字段")

    text = "Agent 岗位要求掌握 LangGraph 与工具调用"
    document = RawDocument(
        doc_id="doc-1",
        requested_url="https://example.com/job",
        final_url="https://example.com/job",
        canonical_url=None,
        title="Agent 招聘",
        content=text,
        content_hash="hash",
        fetched_at=datetime.now(timezone.utc),
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )
    selected = DocumentChunk(
        chunk_id="doc-1:0",
        doc_id="doc-1",
        index=0,
        text=text,
        token_count=12,
        char_start=0,
        char_end=len(text),
    )
    note = build_extractive_note(
        document,
        ChunkSelection(
            chunks=[selected],
            is_relevant=True,
            top1_user_score=0.51,
            top1_active_score=0.82,
            top1_fused_score=0.82,
        ),
        active_query="Agent 框架要求",
        error="invalid_json",
    )
    assert note.compression_status == "extractive_fallback"
    assert note.evidence_snippets == [text]
    assert note.error == "invalid_json"
