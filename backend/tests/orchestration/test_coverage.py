from deeptrace.orchestration.coverage import complete_coverage, forced_coverage


def test_completion_is_sufficient_only_with_sources_note_and_no_gaps(
    research_task, running_coverage, task_completion, research_note
) -> None:
    coverage = running_coverage.model_copy(
        update={
            "successful_source_urls": ["https://a", "https://b"],
            "relevant_note_ids": [research_note.note_id],
        }
    )
    result = complete_coverage(
        research_task, coverage, task_completion, [research_note], []
    )
    assert result.status == "sufficient"


def test_budget_forces_partial_when_a_note_exists(
    research_task, running_coverage, research_note
) -> None:
    result = forced_coverage(
        research_task, running_coverage, [research_note], "task_round_budget"
    )
    assert result.status == "partial"
    assert result.failure_reason == "task_round_budget"
