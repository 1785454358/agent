"""阶段 1 反事实上下文账本和阶段 2 Token 节省指标。"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Sequence

import tiktoken

from deeptrace.models import PageCompressionMetrics, RoundTokenMetrics, TokenUsage


def estimate_usage_cost(
    usage: TokenUsage,
    input_price: Decimal | None,
    output_price: Decimal | None,
) -> Decimal | None:
    """仅用用户显式提供的单价估算模型费用。"""
    if input_price is None or output_price is None:
        return None
    million = Decimal(1_000_000)
    return (
        Decimal(usage.input_tokens) * input_price
        + Decimal(usage.output_tokens) * output_price
    ) / million


class TokenEstimator:
    """使用固定 tokenizer 生成跨轮可比较的估算值。"""
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except ValueError as exc:
            raise ValueError(f"未知 tiktoken encoding：{encoding_name}") from exc

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text or ""))

    @staticmethod
    def _message_data(message: Any) -> dict[str, Any]:
        if isinstance(message, dict):
            return message
        if hasattr(message, "model_dump"):
            return message.model_dump(exclude_none=True)
        return {
            "type": type(message).__name__,
            "content": getattr(message, "content", str(message)),
        }

    def count_messages(self, messages: Sequence[Any]) -> int:
        """序列化角色、正文和 tool_call 元数据，并加入每条消息的固定开销。"""
        total = 0
        for message in messages:
            payload = json.dumps(
                self._message_data(message), ensure_ascii=False,
                sort_keys=True, default=str,
            )
            total += self.count(payload) + 4
        return total + 2 if messages else 0


def calculate_round_metrics(
    round_index: int,
    baseline_context_tokens: int,
    actual_context_tokens: int,
    compression_input_tokens: int = 0,
    compression_output_tokens: int = 0,
    provider_usage: TokenUsage | None = None,
    local_embedding_tokens: int = 0,
) -> RoundTokenMetrics:
    """根据设计公式计算毛节省和扣除压缩调用后的净节省。"""
    gross_saved = baseline_context_tokens - actual_context_tokens
    compression_tokens = compression_input_tokens + compression_output_tokens
    net_saved = gross_saved - compression_tokens
    denominator = max(baseline_context_tokens, 1)
    return RoundTokenMetrics(
        round_index=round_index,
        estimated_baseline_context_tokens=baseline_context_tokens,
        estimated_actual_context_tokens=actual_context_tokens,
        compression_input_tokens=compression_input_tokens,
        compression_output_tokens=compression_output_tokens,
        provider_usage=provider_usage,
        gross_saved_tokens=gross_saved,
        net_saved_tokens=net_saved,
        gross_saving_ratio=gross_saved / denominator,
        net_saving_ratio=net_saved / denominator,
        local_embedding_tokens=local_embedding_tokens,
    )


class TokenLedger:
    """累计阶段 1 会保留的整页正文，并按轮结算阶段 2 实际上下文。"""
    def __init__(self, estimator: TokenEstimator) -> None:
        self.estimator = estimator
        self.baseline_fixed_tokens = 0
        self.baseline_payload_tokens = 0
        self.actual_note_payload_tokens = 0
        self.page_metrics: list[PageCompressionMetrics] = []
        self.round_metrics: list[RoundTokenMetrics] = []
        self._pending_compression_usage = TokenUsage()

    def record_initial_context(self, messages: Sequence[Any]) -> None:
        """登记两个阶段都会携带的系统提示词和用户问题。"""
        self.baseline_fixed_tokens += self.estimator.count_messages(messages)

    def record_assistant(self, message: Any) -> None:
        """累计阶段 1 历史中的 assistant 消息及工具调用元数据。"""
        self.baseline_fixed_tokens += self.estimator.count_messages([message])

    def record_search_tool(self, payload: str) -> None:
        """搜索结果在两个阶段都会进入消息，计入基线固定部分。"""
        self.baseline_fixed_tokens += self.estimator.count(payload)

    def record_fetch_pair(
        self, raw_payload: str, note_payload: str
    ) -> PageCompressionMetrics:
        """原文只进入反事实基线，压缩笔记单独记录页级压缩率。"""
        raw_tokens = self.estimator.count(raw_payload)
        note_tokens = self.estimator.count(note_payload)
        self.baseline_payload_tokens += raw_tokens
        self.actual_note_payload_tokens += note_tokens
        metrics = PageCompressionMetrics(
            raw_tool_payload_tokens=raw_tokens,
            note_tool_payload_tokens=note_tokens,
            compression_ratio=1 - note_tokens / max(raw_tokens, 1),
        )
        self.page_metrics.append(metrics)
        return metrics

    def record_compression_usage(self, usage: TokenUsage) -> None:
        """合并本轮所有并发压缩调用的 Provider usage。"""
        current = self._pending_compression_usage
        self._pending_compression_usage = TokenUsage(
            input_tokens=current.input_tokens + usage.input_tokens,
            output_tokens=current.output_tokens + usage.output_tokens,
            total_tokens=current.total_tokens + usage.total_tokens,
        )

    def finish_round(
        self,
        round_index: int,
        actual_messages: Sequence[Any],
        provider_usage: TokenUsage | None = None,
        local_embedding_tokens: int = 0,
    ) -> RoundTokenMetrics:
        """实际值取真正发给主 Agent 的有界消息，结算后清空本轮压缩用量。"""
        actual = self.estimator.count_messages(actual_messages)
        baseline = self.baseline_fixed_tokens + self.baseline_payload_tokens
        compression = self._pending_compression_usage
        metrics = calculate_round_metrics(
            round_index=round_index,
            baseline_context_tokens=baseline,
            actual_context_tokens=actual,
            compression_input_tokens=compression.input_tokens,
            compression_output_tokens=compression.output_tokens,
            provider_usage=provider_usage,
            local_embedding_tokens=local_embedding_tokens,
        )
        self.round_metrics.append(metrics)
        self._pending_compression_usage = TokenUsage()
        return metrics


def format_round_metrics(metrics: RoundTokenMetrics) -> str:
    """生成适合 CLI 的单行逐轮统计。"""
    compression = metrics.compression_input_tokens + metrics.compression_output_tokens
    return (
        f"[Round {metrics.round_index}] "
        f"baseline≈{metrics.estimated_baseline_context_tokens:,} | "
        f"actual≈{metrics.estimated_actual_context_tokens:,} | "
        f"gross saved≈{metrics.gross_saved_tokens:,} "
        f"({metrics.gross_saving_ratio:.1%}) | "
        f"compression={compression:,} | "
        f"net saved≈{metrics.net_saved_tokens:,} "
        f"({metrics.net_saving_ratio:.1%})"
    )


def format_token_summary(metrics: Sequence[RoundTokenMetrics]) -> str:
    """汇总整次研究的估算节省，并将 Provider usage 独立展示。"""
    gross = sum(item.gross_saved_tokens for item in metrics)
    net = sum(item.net_saved_tokens for item in metrics)
    compression = sum(
        item.compression_input_tokens + item.compression_output_tokens for item in metrics
    )
    provider_input = sum(
        item.provider_usage.input_tokens
        for item in metrics if item.provider_usage is not None
    )
    provider_output = sum(
        item.provider_usage.output_tokens
        for item in metrics if item.provider_usage is not None
    )
    return (
        "Token 汇总（上下文为估算值）\n"
        f"累计毛节省≈{gross:,} | 压缩调用={compression:,} | 累计净节省≈{net:,}\n"
        f"主 Agent Provider usage: input={provider_input:,}, output={provider_output:,}"
    )
