from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deeptrace.models import RawDocument, ScraperUsed, TokenUsage
from deeptrace.state import append_unique, merge_dicts


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


def test_append_unique_keeps_first_seen_order() -> None:
    assert append_unique(["q1", "q2"], ["q2", "q3"]) == ["q1", "q2", "q3"]


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
