"""Provider token usage models."""

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
    executor: TokenUsage = Field(default_factory=TokenUsage)
    replanner: TokenUsage = Field(default_factory=TokenUsage)
    supervisor: TokenUsage = Field(default_factory=TokenUsage)
    researcher: TokenUsage = Field(default_factory=TokenUsage)
    writer: TokenUsage = Field(default_factory=TokenUsage)

    @property
    def total(self) -> TokenUsage:
        return add_token_usages(
            self.planner,
            self.executor,
            self.replanner,
            self.supervisor,
            self.researcher,
            self.writer,
        )
