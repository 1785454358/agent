from pathlib import Path

from deeptrace.embedding import (
    CompressionRuntime,
    chunk_document,
    select_relevant_chunks,
)
from deeptrace.models import RawDocument, ScraperUsed


MODEL_PATH = Path(r"D:\Dev\Models\bge-m3")


def _document(doc_id: str, content: str) -> RawDocument:
    from datetime import datetime, timezone

    return RawDocument(
        doc_id=doc_id,
        requested_url="https://example.com",
        final_url="https://example.com",
        canonical_url=None,
        title="测试页面",
        content=content,
        content_hash="hash",
        fetched_at=datetime.now(timezone.utc),
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )


def test_real_bge_uses_dual_query_max_and_short_circuits_irrelevant_page() -> None:
    """防止实现改成平均融合，或无关页面仍进入压缩调用。"""
    runtime = CompressionRuntime(MODEL_PATH, batch_size=8)
    relevant = _document(
        "jobs",
        "公司招聘概览。Agent 开发岗位要求熟悉 LangGraph、工具调用与 RAG。",
    )
    chunks = chunk_document(runtime, relevant, chunk_tokens=800, overlap_tokens=100)
    selection = select_relevant_chunks(
        runtime,
        chunks,
        user_query="今年互联网公司的校园招聘要求",
        active_query="Agent 开发需要掌握哪些框架",
        top_k=2,
        threshold=0.45,
    )

    assert selection.is_relevant
    assert "LangGraph" in " ".join(chunk.text for chunk in selection.chunks)
    assert selection.top1_fused_score == max(
        selection.top1_user_score, selection.top1_active_score
    )

    unrelated = _document("recipe", "黄油曲奇的烘焙温度、面粉比例和烤箱预热方法。")
    unrelated_chunks = chunk_document(
        runtime, unrelated, chunk_tokens=800, overlap_tokens=100
    )
    irrelevant = select_relevant_chunks(
        runtime,
        unrelated_chunks,
        user_query="量子纠错码的最新研究进展",
        active_query="表面码逻辑错误率实验数据",
        top_k=2,
        threshold=0.45,
    )
    assert irrelevant.top1_fused_score < 0.45
    assert not irrelevant.is_relevant
    assert irrelevant.chunks == []
