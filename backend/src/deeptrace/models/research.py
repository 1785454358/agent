"""研究笔记和压缩结果模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from deeptrace.models.metrics import TokenUsage


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
    compression_status: Literal["compressed", "extractive_fallback", "irrelevant"]
    error: str | None = None


class CompressionOutcome(BaseModel):
    """并发压缩结果，用 tool_call_id 防止工具响应错配。"""

    tool_call_id: str
    note: ResearchNote | None
    error: str | None = None
    order: int = Field(ge=0)
    usage: TokenUsage = Field(default_factory=TokenUsage)
