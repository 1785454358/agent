from datetime import UTC, datetime

from deeptrace.memory import ResearchMemory
from deeptrace.models import RawDocument, ScraperUsed


def _document(url: str, content: str) -> RawDocument:
    return RawDocument(
        doc_id=f"doc-{url}",
        requested_url=url,
        final_url=url,
        canonical_url=None,
        title=f"标题{url}",
        content=content,
        content_hash=f"hash-{url}-{len(content)}",
        fetched_at=datetime(2024, 12, 1, tzinfo=UTC),
        source_published_at=datetime(2024, 6, 1, tzinfo=UTC),
        scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )


def test_memory_roundtrip_and_dedup(tmp_path) -> None:
    memory = ResearchMemory(tmp_path / "notes.jsonl")
    document = _document("https://example.com/a", "页面正文")

    assert memory.lookup("https://example.com/a") is None

    assert memory.add_documents([document]) == 1
    # 重新加载验证持久化
    reloaded = ResearchMemory(tmp_path / "notes.jsonl")
    entry = reloaded.lookup("https://example.com/a")
    assert entry is not None
    assert entry.content == "页面正文"
    assert entry.published_at is not None
    # 相同内容哈希不重复写入
    assert reloaded.add_documents([document]) == 0
    # 还原为可复用文档
    restored = reloaded.entry_to_document(entry)
    assert restored.content == "页面正文"
    assert restored.status == "success"


def test_memory_skips_failed_documents(tmp_path) -> None:
    memory = ResearchMemory(tmp_path / "notes.jsonl")
    failed = _document("https://example.com/b", "x").model_copy(
        update={"status": "failed", "content": ""}
    )
    assert memory.add_documents([failed]) == 0
    assert memory.entries() == []
