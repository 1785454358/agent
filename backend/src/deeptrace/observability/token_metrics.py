"""Provider usage formatting and optional cost estimation."""

from __future__ import annotations

from decimal import Decimal

from deeptrace.models import TokenUsage, UsageBreakdown


def estimate_usage_cost(
    usage: TokenUsage,
    input_price: Decimal | None,
    output_price: Decimal | None,
) -> Decimal | None:
    """Estimate cost only when both explicit per-million-token prices exist."""
    if input_price is None or output_price is None:
        return None
    million = Decimal(1_000_000)
    return (
        Decimal(usage.input_tokens) * input_price
        + Decimal(usage.output_tokens) * output_price
    ) / million


def format_role_usage(usage: UsageBreakdown) -> str:
    """Render the only Provider-consuming roles in the Basic pipeline."""
    return (
        "Provider Token（按角色）\n"
        f"Planner: {usage.planner.total_tokens:,}\n"
        f"Writer: {usage.writer.total_tokens:,}\n"
        f"Total: {usage.total.total_tokens:,}"
    )
