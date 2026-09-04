from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deeptrace.models import RawDocument, ScraperUsed, TokenUsage, UsageBreakdown
from deeptrace.orchestration.state import (
    GraphState,
    append_unique,
    merge_dicts,
    merge_token_usage,
    merge_usage_breakdown,
)


def test_usage_roles_and_state_fields_are_present() -> None:
    usage = merge_usage_breakdown(
        UsageBreakdown(researcher=TokenUsage(total_tokens=3)),
        UsageBreakdown(writer=TokenUsage(total_tokens=5)),
    )

    assert usage.researcher.total_tokens == 3
    assert usage.writer.total_tokens == 5
    assert usage.total.total_tokens == 8
    assert "final_sources" in GraphState.__annotations__
    assert "used_claim_ids" not in GraphState.__annotations__
    assert "verification_results" not in GraphState.__annotations__


def test_merge_dicts_preserves_old_entries_and_overwrites_same_key() -> None:
    assert merge_dicts({"a": 1, "b": 2}, {"b": 3, "c": 4}) == {
        "a": 1,
        "b": 3,
        "c": 4,
    }


def test_merge_dicts_does_not_mutate_input() -> None:
    left = {"a": 1}
    right = {"b": 2}

    merge_dicts(left, right)

    assert left == {"a": 1}
    assert right == {"b": 2}


def test_merge_dicts_removes_explicit_tombstones() -> None:
    assert merge_dicts(
        {"resolved-gap": "old", "other-gap": "keep"},
        {"resolved-gap": None},
    ) == {"other-gap": "keep"}


def test_append_unique_keeps_first_seen_order() -> None:
    assert append_unique(["q1", "q2"], ["q2", "q3"]) == ["q1", "q2", "q3"]


def test_merge_token_usage_sums_each_counter_without_mutating_inputs() -> None:
    left = TokenUsage(input_tokens=10, output_tokens=4, total_tokens=14)
    right = TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10)

    result = merge_token_usage(left, right)

    assert result == TokenUsage(input_tokens=17, output_tokens=7, total_tokens=24)
    assert left == TokenUsage(input_tokens=10, output_tokens=4, total_tokens=14)
    assert right == TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10)


def test_raw_document_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        RawDocument(
            doc_id="doc-1",
            requested_url="https://example.com/a",
            final_url="https://example.com/a",
            canonical_url=None,
            title="示例",
            content="正文",
            content_hash="hash",
            fetched_at=datetime.now(UTC),
            scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
            status="unknown",
        )


def test_token_usage_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=-1)
