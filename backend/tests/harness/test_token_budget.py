from __future__ import annotations

from deeptrace.harness.token_budget import (
    Segment,
    SegmentPriority,
    TokenBudgetConfig,
    assemble_with_budget,
    count_tokens,
    truncate_to_tokens,
)


def test_count_tokens_and_truncate_respect_the_limit() -> None:
    text = "word " * 200
    total = count_tokens(text)
    assert total > 0

    shortened = truncate_to_tokens(text, total // 2)
    assert count_tokens(shortened) <= total // 2
    assert count_tokens(shortened) < total


def test_pinned_segments_survive_a_tiny_budget() -> None:
    config = TokenBudgetConfig(
        context_tokens=300, output_reserve_tokens=200, safety_tokens=0
    )
    pinned = Segment(
        "output_contract",
        '只输出 JSON：{"content": "..."}。',
        SegmentPriority.PINNED,
    )
    elastic = Segment("elastic", "word " * 500, SegmentPriority.NORMAL)

    text, allocation = assemble_with_budget([pinned, elastic], config)

    assert pinned.text in text
    assert allocation.dropped == ["elastic"]
    assert allocation.pinned_overflow is False
    assert allocation.bound is True


def test_elastic_segment_is_shortened_to_its_floor_before_being_dropped() -> None:
    elastic_text = "word " * 200
    limit = count_tokens(elastic_text)
    config = TokenBudgetConfig(
        context_tokens=limit, output_reserve_tokens=10, safety_tokens=0
    )
    segment = Segment(
        "source_1", elastic_text, SegmentPriority.NORMAL, min_tokens=20
    )

    text, allocation = assemble_with_budget([segment], config)

    assert allocation.truncated == ["source_1"]
    assert allocation.dropped == []
    assert 0 < count_tokens(text) < limit


def test_budget_stays_unbound_when_everything_fits() -> None:
    config = TokenBudgetConfig(
        context_tokens=100_000, output_reserve_tokens=4_096, safety_tokens=2_048
    )
    segments = [
        Segment("instructions", "指令 " * 10, SegmentPriority.PINNED),
        Segment("sources", "资料 " * 50, SegmentPriority.NORMAL),
    ]

    text, allocation = assemble_with_budget(segments, config)

    assert allocation.bound is False
    assert allocation.dropped == []
    assert allocation.truncated == []
    assert "资料" in text


def test_output_reserve_is_subtracted_from_the_input_budget() -> None:
    config = TokenBudgetConfig(
        context_tokens=10_000, output_reserve_tokens=6_000, safety_tokens=1_000
    )

    assert config.input_budget == 3_000


def test_allocation_reports_actual_retained_tokens_and_pinned_overflow() -> None:
    text, allocation = assemble_with_budget(
        [Segment("fixed", "word " * 100, SegmentPriority.PINNED)],
        TokenBudgetConfig(context_tokens=10, output_reserve_tokens=0, safety_tokens=0),
    )
    assert allocation.pinned_overflow
    assert allocation.used_tokens == count_tokens(text)
    text, allocation = assemble_with_budget(
        [Segment("elastic", "word " * 100, min_tokens=1)],
        TokenBudgetConfig(context_tokens=10, output_reserve_tokens=0, safety_tokens=0),
    )
    assert allocation.included["elastic"] == count_tokens(text)
