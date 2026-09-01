import pytest

from deeptrace.agent.researcher import parse_task_completion
from deeptrace.models import VerificationGap
from deeptrace.prompts.researcher import build_researcher_messages


def test_parse_task_completion_rejects_wrong_task() -> None:
    call = {
        "name": "complete_research_task",
        "args": {
            "task_id": "task-02",
            "summary": "已完成",
            "covered_topics": ["工具调用"],
            "unresolved_topics": [],
        },
    }

    with pytest.raises(ValueError, match="task_id"):
        parse_task_completion(call, expected_task_id="task-01")


def test_researcher_prompt_contains_current_task_but_not_raw_document(
    research_task, task_coverage, research_note
) -> None:
    messages = build_researcher_messages(
        user_query="年度进展",
        task=research_task,
        coverage=task_coverage,
        notes=[research_note],
        recent_messages=[],
        budget_summary="剩余 2 轮",
    )
    serialized = "\n".join(str(message.content) for message in messages)

    assert research_task.question in serialized
    assert research_note.key_points[0] in serialized
    assert "整页正文唯一标记" not in serialized


def test_supplement_prompt_contains_gaps_and_existing_domains(
    research_task, task_coverage, research_note
) -> None:
    gap = VerificationGap(
        gap_id="gap-01",
        task_id=research_task.task_id,
        section_id=research_task.section_id,
        claim_id="claim-01",
        reason_code="source_independence_insufficient",
        description="缺少第二个独立来源",
        suggested_query="关键主张 官方公告",
        preferred_source_kinds=["official", "academic"],
        priority="high",
    )

    messages = build_researcher_messages(
        user_query="年度进展",
        task=research_task,
        coverage=task_coverage,
        notes=[research_note],
        recent_messages=[],
        budget_summary="补搜 1 轮",
        verification_gaps=[gap],
        existing_source_identities=["example.com"],
        research_mode="supplement",
    )
    serialized = "\n".join(str(message.content) for message in messages)

    assert gap.description in serialized
    assert "official" in serialized
    assert "example.com" in serialized
    assert "补搜模式" in serialized
    assert "整页正文唯一标记" not in serialized
