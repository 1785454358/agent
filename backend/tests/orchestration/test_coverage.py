from deeptrace.orchestration.coverage import complete_coverage, forced_coverage


def test_completion_is_sufficient_only_with_sources_note_and_no_gaps(
    research_task, running_coverage, task_completion, research_note
) -> None:
    first = research_note.model_copy(
        update={
            "source_url": "https://openai.com/research/a",
            "source_kind": "official",
        }
    )
    second = research_note.model_copy(
        update={
            "note_id": "note-02",
            "doc_id": "doc-02",
            "source_url": "https://arxiv.org/abs/2401.00001",
            "source_kind": "academic",
        }
    )
    coverage = running_coverage.model_copy(
        update={
            "successful_source_urls": [first.source_url, second.source_url],
            "relevant_note_ids": [first.note_id, second.note_id],
        }
    )
    result = complete_coverage(
        research_task, coverage, task_completion, [first, second], []
    )
    assert result.status == "sufficient"


def test_two_urls_on_one_domain_do_not_satisfy_diversity(
    research_task, running_coverage, task_completion, research_note
) -> None:
    first = research_note.model_copy(
        update={"source_url": "https://www.openai.com/a", "source_kind": "official"}
    )
    second = research_note.model_copy(
        update={
            "note_id": "note-02",
            "source_url": "https://research.openai.com/b",
            "source_kind": "official",
        }
    )

    result = complete_coverage(
        research_task, running_coverage, task_completion, [first, second], []
    )

    assert result.status == "partial"


def test_budget_forces_partial_when_a_note_exists(
    research_task, running_coverage, research_note
) -> None:
    result = forced_coverage(
        research_task, running_coverage, [research_note], "task_round_budget"
    )
    assert result.status == "partial"
    assert result.failure_reason == "task_round_budget"
