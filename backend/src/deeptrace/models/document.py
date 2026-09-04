"""网页抓取、分块和待处理调用的数据模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class PendingFetch(BaseModel):
    """一次尚未处理的网页抓取工具调用。"""

    tool_call_id: str
    url: str
    active_query: str
    task_id: str
    section_id: str
    order: int = Field(ge=0)


class ScraperUsed(StrEnum):
    """最终提供正文的抓取及提取路径。"""

    SEARCH_PROVIDER = "search_provider"
    HTTPX_TRAFILATURA = "httpx_trafilatura"
    HTTPX_BS4 = "httpx_bs4"
    PLAYWRIGHT_TRAFILATURA = "playwright_trafilatura"
    PLAYWRIGHT_BS4 = "playwright_bs4"


class RawDocument(BaseModel):
    """抓取后的原始文档；正文只保存在 State 文档区。"""

    doc_id: str
    requested_url: str
    final_url: str
    canonical_url: str | None
    title: str
    content: str
    content_hash: str
    fetched_at: datetime
    scraper_used: ScraperUsed
    status: Literal["success", "irrelevant", "failed"]
    error: str | None = None
    source_published_at: datetime | None = None
    source_modified_at: datetime | None = None
    publisher: str | None = None


class DocumentChunk(BaseModel):
    """带原文定位信息的文本块，不保存 numpy 向量。"""

    chunk_id: str
    doc_id: str
    index: int = Field(ge=0)
    text: str
    token_count: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
