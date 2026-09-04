"""研究记忆：跨运行复用已抓取页面与笔记元数据。

记忆只保存带来源 URL、标题、发布时间与抓取时间的一手页面正文。
命中记忆的 URL 在后续运行中免网络抓取，直接进入召回与压缩；
是否启用由 DEEPTRACE_USE_MEMORY 控制，存储为运行目录下的 JSONL。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field

from deeptrace.models import RawDocument


class MemoryEntry(BaseModel):
    """一条可跨运行复用的页面记忆。"""

    url: str = Field(min_length=1)
    title: str = ""
    content: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    published_at: datetime | None = None
    fetched_at: datetime


def _entry_from_document(document: RawDocument) -> MemoryEntry:
    return MemoryEntry(
        url=document.final_url or document.requested_url,
        title=document.title,
        content=document.content,
        content_hash=document.content_hash,
        published_at=document.source_published_at,
        fetched_at=document.fetched_at,
    )


class ResearchMemory:
    """基于 JSONL 追加文件的研究记忆仓库。"""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._by_url: dict[str, MemoryEntry] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = MemoryEntry.model_validate_json(line)
                except Exception:
                    continue
                self._by_url[entry.url] = entry

    def lookup(self, url: str) -> MemoryEntry | None:
        """按最终 URL 查询记忆；命中返回已存页面。"""
        self._load()
        return self._by_url.get(url)

    def entries(self) -> list[MemoryEntry]:
        self._load()
        return list(self._by_url.values())

    def add_documents(self, documents: Sequence[RawDocument]) -> int:
        """把本次运行成功抓取的页面写入记忆；重复 URL 按内容哈希去重。"""
        self._load()
        written = 0
        with self._path.open("a", encoding="utf-8") as handle:
            for document in documents:
                if document.status != "success" or not document.content:
                    continue
                entry = _entry_from_document(document)
                existing = self._by_url.get(entry.url)
                if existing is not None and existing.content_hash == entry.content_hash:
                    continue
                handle.write(entry.model_dump_json() + "\n")
                self._by_url[entry.url] = entry
                written += 1
        return written

    def entry_to_document(self, entry: MemoryEntry) -> RawDocument:
        """把记忆还原为可复用的 RawDocument（doc_id 由 URL 哈希派生）。"""
        doc_id = "mem-" + hashlib.sha256(entry.url.encode("utf-8")).hexdigest()[:20]
        return RawDocument(
            doc_id=doc_id,
            requested_url=entry.url,
            final_url=entry.url,
            canonical_url=None,
            title=entry.title or entry.url,
            content=entry.content,
            content_hash=entry.content_hash,
            fetched_at=entry.fetched_at,
            source_published_at=entry.published_at,
            scraper_used="httpx_trafilatura",
            status="success",
        )


def default_memory_path() -> Path:
    """默认记忆文件路径：DEEPTRACE_MEMORY_PATH 或 backend/memory/notes.jsonl。"""
    env = os.getenv("DEEPTRACE_MEMORY_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "memory" / "notes.jsonl"
