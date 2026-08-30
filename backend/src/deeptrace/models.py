"""阶段 2 在图节点之间传递的强类型数据模型。"""

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
    order: int = Field(ge=0)


class ScraperUsed(StrEnum):
    """最终提供正文的抓取及提取路径。"""

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


class DocumentChunk(BaseModel):
    """带原文定位信息的文本块，不保存 numpy 向量。"""

    chunk_id: str
    doc_id: str
    index: int = Field(ge=0)
    text: str
    token_count: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class ResearchNote(BaseModel):
    """供主 Agent 消费的压缩研究笔记。"""

    note_id: str
    doc_id: str
    active_query: str
    title: str
    key_points: list[str]
    evidence_snippets: list[str]
    source_url: str
    relevance_score: float = Field(ge=-1.0, le=1.0)
    compression_status: Literal[
        "compressed", "extractive_fallback", "irrelevant"
    ]
    error: str | None = None


class TokenUsage(BaseModel):
    """一次模型调用返回或估算的 Token 用量。"""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ContextAudit(BaseModel):
    """记录主 Agent 上下文是否意外包含整页原文。"""

    round_index: int = Field(ge=1)
    input_tokens: int = Field(ge=0)
    raw_content_match_count: int = Field(ge=0)


class PageCompressionMetrics(BaseModel):
    """单个网页从原始载荷压缩为笔记后的估算指标。"""

    raw_tool_payload_tokens: int = Field(ge=0)
    note_tool_payload_tokens: int = Field(ge=0)
    compression_ratio: float


class RoundTokenMetrics(BaseModel):
    """一轮主 Agent 调用的反事实基线与实际 Token 指标。"""

    round_index: int = Field(ge=1)
    estimated_baseline_context_tokens: int = Field(ge=0)
    estimated_actual_context_tokens: int = Field(ge=0)
    compression_input_tokens: int = Field(default=0, ge=0)
    compression_output_tokens: int = Field(default=0, ge=0)
    provider_usage: TokenUsage | None = None
    gross_saved_tokens: int
    net_saved_tokens: int
    gross_saving_ratio: float
    net_saving_ratio: float
    local_embedding_tokens: int = Field(default=0, ge=0)


class CompressionOutcome(BaseModel):
    """并发压缩结果，用 tool_call_id 防止工具响应错配。"""

    tool_call_id: str
    note: ResearchNote | None
    error: str | None = None
    order: int = Field(ge=0)
