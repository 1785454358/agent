from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deeptrace.models import RawDocument, ScraperUsed, TokenUsage, UsageBreakdown
from deeptrace.orchestration.state import (
    GraphState,
    merge_dicts,
    merge_stage_seconds,
    merge_token_usage,
    merge_usage_breakdown,
)


def test_graph_state_has_only_basic_research_data() -> None:
    annotations = GraphState.__annotations__

    assert {
        "user_query",
        "search_queries",
        "initial_search",
        "documents",
        "research_context",
        "final_sources",
    } <= annotations.keys()
    assert not (
        {
            "notes",
            "chunks",
            "research_plan",
            "task_coverages",
            "section_results",
            "used_note_ids",
        }
        & annotations.keys()
    )


def test_usage_has_only_planner_and_writer_roles() -> None:
    usage = merge_usage_breakdown(
        UsageBreakdown(planner=TokenUsage(total_tokens=3)),
        UsageBreakdown(writer=TokenUsage(total_tokens=5)),
    )

    assert usage.planner.total_tokens == 3
    assert usage.writer.total_tokens == 5
    assert usage.total.total_tokens == 8
    assert set(UsageBreakdown.model_fields) == {"planner", "writer"}


def test_merge_dicts_supports_overwrite_and_tombstones_without_mutation() -> None:
    left = {"a": 1, "b": 2}
    right = {"b": None, "c": 4}

    assert merge_dicts(left, right) == {"a": 1, "c": 4}
    assert left == {"a": 1, "b": 2}
    assert right == {"b": None, "c": 4}


def test_usage_and_stage_reducers_sum_without_mutating_inputs() -> None:
    left = TokenUsage(input_tokens=10, output_tokens=4, total_tokens=14)
    right = TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10)

    assert merge_token_usage(left, right) == TokenUsage(
        input_tokens=17, output_tokens=7, total_tokens=24
    )
    assert merge_stage_seconds({"plan": 1.0}, {"plan": 0.5, "writer": 2.0}) == {
        "plan": 1.5,
        "writer": 2.0,
    }
    assert left.total_tokens == 14
    assert right.total_tokens == 10


def test_raw_document_and_token_usage_validate_inputs() -> None:
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
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=-1)
