from deeptrace.orchestration.quality import (
    note_is_valid,
    source_identity,
    summarize_note_quality,
)


def test_retrospective_is_valid_but_out_of_range_is_not(research_note) -> None:
    review = research_note.model_copy(
        update={
            "note_id": "note-review",
            "source_url": "https://openai.com/review",
            "source_kind": "official",
            "temporal_relation": "retrospective",
        }
    )
    later = research_note.model_copy(
        update={
            "note_id": "note-later",
            "source_url": "https://example.org/later",
            "source_kind": "reputable_secondary",
            "temporal_relation": "out_of_range",
        }
    )

    summary = summarize_note_quality([review, later])

    assert note_is_valid(review)
    assert not note_is_valid(later)
    assert summary.valid_ids == ["note-review"]
    assert summary.out_of_range_ids == ["note-later"]
    assert summary.qualified_urls == ["https://openai.com/review"]


def test_source_identity_uses_registered_domain() -> None:
    assert source_identity("https://research.example.co.uk/a") == "example.co.uk"
    assert source_identity("https://www.example.co.uk/b") == "example.co.uk"
