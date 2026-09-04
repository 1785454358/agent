from decimal import Decimal

from deeptrace.models import TokenUsage, UsageBreakdown
from deeptrace.observability import estimate_usage_cost, format_role_usage


def test_estimate_usage_cost_uses_explicit_prices() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)

    assert estimate_usage_cost(usage, Decimal("2"), Decimal("6")) == Decimal("5")
    assert estimate_usage_cost(usage, None, Decimal("6")) is None


def test_role_usage_renders_only_planner_and_writer() -> None:
    rendered = format_role_usage(
        UsageBreakdown(
            planner=TokenUsage(total_tokens=7),
            writer=TokenUsage(total_tokens=11),
        )
    )

    assert "Planner: 7" in rendered
    assert "Writer: 11" in rendered
    assert "Researcher" not in rendered
    assert "Compression" not in rendered
    assert "Total: 18" in rendered
