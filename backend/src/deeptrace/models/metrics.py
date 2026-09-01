"""模型调用、上下文审计和 Token 统计模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """一次模型调用返回或估算的 Token 用量。"""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


def add_token_usages(*items: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        total_tokens=sum(item.total_tokens for item in items),
    )


class UsageBreakdown(BaseModel):
    """各模型角色的真实 Provider usage。"""
    planner: TokenUsage = Field(default_factory=TokenUsage)
    researcher: TokenUsage = Field(default_factory=TokenUsage)
    compression: TokenUsage = Field(default_factory=TokenUsage)
    writer: TokenUsage = Field(default_factory=TokenUsage)
    claim_extractor: TokenUsage = Field(default_factory=TokenUsage)
    verifier: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def total(self) -> TokenUsage:
        return add_token_usages(
            self.planner,
            self.researcher,
            self.compression,
            self.writer,
            self.claim_extractor,
            self.verifier,
        )


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
