import pytest

from deeptrace.models import TokenUsage
from deeptrace.observability import (
    TokenEstimator,
    TokenLedger,
    calculate_round_metrics,
    format_role_usage,
)


def test_token_metrics_compute_net_saving_and_accumulate_raw_baseline() -> None:
    """防止把压缩成本遗漏，或只统计当前页而低估后续轮次基线。"""
    metrics = calculate_round_metrics(
        round_index=4,
        baseline_context_tokens=32_180,
        actual_context_tokens=8_420,
        compression_input_tokens=1_800,
        compression_output_tokens=340,
    )
    assert metrics.gross_saved_tokens == 23_760
    assert metrics.net_saved_tokens == 21_620
    assert metrics.gross_saving_ratio == pytest.approx(0.7383, abs=0.0001)
    assert metrics.net_saving_ratio == pytest.approx(0.6718, abs=0.0001)

    ledger = TokenLedger(TokenEstimator("cl100k_base"))
    first_page = ledger.record_fetch_pair("原文一" * 1000, "笔记一")
    first_total = ledger.baseline_payload_tokens
    second_page = ledger.record_fetch_pair("原文二" * 1000, "笔记二")
    assert ledger.baseline_payload_tokens > first_total
    assert ledger.baseline_payload_tokens == (
        first_page.raw_tool_payload_tokens + second_page.raw_tool_payload_tokens
    )

    ledger.record_compression_usage(TokenUsage(input_tokens=20, output_tokens=5))
    round_metrics = ledger.finish_round(
        round_index=1,
        actual_messages=[{"role": "user", "content": "请调研 Agent 岗位"}],
        provider_usage=TokenUsage(input_tokens=10, output_tokens=4, total_tokens=14),
    )
    assert round_metrics.compression_input_tokens == 20
    assert round_metrics.compression_output_tokens == 5
    assert round_metrics.provider_usage is not None
    assert round_metrics.provider_usage.total_tokens == 14


def test_role_usage_includes_claim_extractor_and_verifier() -> None:
    from deeptrace.models import UsageBreakdown

    rendered = format_role_usage(
        UsageBreakdown(
            claim_extractor=TokenUsage(total_tokens=7),
            verifier=TokenUsage(total_tokens=11),
        )
    )

    assert "Claim Extractor: 7" in rendered
    assert "Verifier: 11" in rendered
