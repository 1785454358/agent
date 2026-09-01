"""阶段 3 的确定性基础覆盖判断。"""

from __future__ import annotations

from typing import Sequence

from deeptrace.models import (
    ResearchNote,
    ResearchTask,
    TaskCompletion,
    TaskCoverage,
)


def _task_notes(
    task: ResearchTask, notes: Sequence[ResearchNote]
) -> list[ResearchNote]:
    return [
        note
        for note in notes
        if note.task_id == task.task_id and note.compression_status != "irrelevant"
    ]


def complete_coverage(
    task: ResearchTask,
    previous: TaskCoverage,
    completion: TaskCompletion,
    notes: Sequence[ResearchNote],
    errors: Sequence[str],
) -> TaskCoverage:
    """Researcher 显式完成时根据来源、笔记与缺口确定状态。"""
    relevant = _task_notes(task, notes)
    sources = list(
        dict.fromkeys(
            [*previous.successful_source_urls, *(note.source_url for note in relevant)]
        )
    )
    note_ids = list(
        dict.fromkeys([*previous.relevant_note_ids, *(note.note_id for note in relevant)])
    )
    sufficient = (
        len(sources) >= task.min_sources
        and bool(note_ids)
        and not completion.unresolved_topics
    )
    status = "sufficient" if sufficient else ("partial" if note_ids else "failed")
    failure_reason = None
    if status != "sufficient":
        failure_reason = errors[0] if errors else "insufficient_coverage"
    return previous.model_copy(
        update={
            "status": status,
            "successful_source_urls": sources,
            "relevant_note_ids": note_ids,
            "covered_topics": list(dict.fromkeys(completion.covered_topics)),
            "missing_topics": list(dict.fromkeys(completion.unresolved_topics)),
            "failure_reason": failure_reason,
        }
    )


def forced_coverage(
    task: ResearchTask,
    previous: TaskCoverage,
    notes: Sequence[ResearchNote],
    reason: str,
) -> TaskCoverage:
    """预算或空转强制结束时，有笔记为 partial，否则 failed。"""
    relevant = _task_notes(task, notes)
    sources = list(
        dict.fromkeys(
            [*previous.successful_source_urls, *(note.source_url for note in relevant)]
        )
    )
    note_ids = list(
        dict.fromkeys([*previous.relevant_note_ids, *(note.note_id for note in relevant)])
    )
    covered = set(previous.covered_topics)
    missing = [topic for topic in task.expected_topics if topic not in covered]
    return previous.model_copy(
        update={
            "status": "partial" if note_ids else "failed",
            "successful_source_urls": sources,
            "relevant_note_ids": note_ids,
            "missing_topics": missing,
            "failure_reason": reason,
        }
    )
