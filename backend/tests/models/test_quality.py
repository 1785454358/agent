from deeptrace.models import TaskCoverage


def test_quality_defaults(raw_document, research_note, research_task) -> None:
    coverage = TaskCoverage(task_id=research_task.task_id)

    assert raw_document.source_published_at is None
    assert raw_document.source_modified_at is None
    assert raw_document.publisher is None
    assert research_note.source_kind == "unknown"
    assert research_note.temporal_relation == "not_applicable"
    assert research_note.event_start_date is None
    assert research_note.event_end_date is None
    assert coverage.valid_note_ids == []
    assert coverage.out_of_range_note_ids == []
