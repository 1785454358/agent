import pytest
from pydantic import ValidationError

from deeptrace.multi_agent.models import (
    PlannedTask,
    ResearchAssignment,
    ResearcherResult,
)
from deeptrace.multi_agent.state import (
    compact_task_history,
    leaf_gaps,
    open_leaf_tasks,
    ready_task_ids,
)


def assignment(task_id: str, *, parents: tuple[str, ...] = ()) -> ResearchAssignment:
    return ResearchAssignment(
        id=task_id,
        objective=f"研究 {task_id}",
        required_outputs=[f"{task_id} 检查项"],
        excluded_scope=["排除重复内容"],
        source_guidance=["官方来源"],
        parent_ids=list(parents),
    )


def result(
    task_id: str, status: str, gaps: tuple[str, ...] = ()
) -> ResearcherResult:
    return ResearcherResult(
        task_id=task_id,
        status=status,
        summary=f"{task_id} 结果",
        source_urls=(
            [] if status == "blocked" else [f"https://example.com/{task_id}"]
        ),
        gaps=list(gaps),
        stop_reason="completed" if status == "completed" else "round_limit",
    )


def test_terminal_task_requires_matching_result():
    with pytest.raises(ValidationError, match="terminal task status"):
        PlannedTask(assignment=assignment("r1"), status="partial")
    with pytest.raises(ValidationError, match="result ID"):
        PlannedTask(
            assignment=assignment("r1"),
            status="completed",
            result=result("r2", "completed"),
        )


def test_ready_tasks_require_executed_parents():
    tasks = {
        "r1": PlannedTask(assignment=assignment("r1")),
        "r2": PlannedTask(assignment=assignment("r2", parents=("r1",))),
    }
    assert ready_task_ids(tasks) == ["r1"]
    tasks["r1"] = PlannedTask(
        assignment=assignment("r1"),
        status="partial",
        result=result("r1", "partial", ("发布日期未确认",)),
    )
    assert ready_task_ids(tasks) == ["r2"]


def test_pending_child_does_not_hide_parent_gap():
    tasks = {
        "r1": PlannedTask(
            assignment=assignment("r1"),
            status="partial",
            result=result("r1", "partial", ("旧缺口",)),
        ),
        "r2": PlannedTask(assignment=assignment("r2", parents=("r1",))),
    }
    assert [task.assignment.id for task in open_leaf_tasks(tasks)] == ["r1"]
    assert leaf_gaps(tasks) == ["旧缺口"]


def test_completed_followup_supersedes_parent_gap():
    tasks = {
        "r1": PlannedTask(
            assignment=assignment("r1"),
            status="partial",
            result=result("r1", "partial", ("旧缺口",)),
        ),
        "r2": PlannedTask(
            assignment=assignment("r2", parents=("r1",)),
            status="completed",
            result=result("r2", "completed"),
        ),
    }
    assert open_leaf_tasks(tasks) == []
    assert leaf_gaps(tasks) == []


def test_partial_followup_replaces_parent_gap_with_latest_gap():
    tasks = {
        "r1": PlannedTask(
            assignment=assignment("r1"),
            status="partial",
            result=result("r1", "partial", ("旧缺口",)),
        ),
        "r2": PlannedTask(
            assignment=assignment("r2", parents=("r1",)),
            status="partial",
            result=result("r2", "partial", ("新缺口",)),
        ),
    }
    assert leaf_gaps(tasks) == ["新缺口"]


def test_compact_history_omits_urls_and_page_text():
    tasks = {
        "r1": PlannedTask(
            assignment=assignment("r1"),
            status="partial",
            result=result("r1", "partial", ("仍缺官方文件",)),
        )
    }
    history = compact_task_history(tasks)
    assert history == [
        {
            "id": "r1",
            "objective": "研究 r1",
            "required_outputs": ["r1 检查项"],
            "excluded_scope": ["排除重复内容"],
            "source_guidance": ["官方来源"],
            "parent_ids": [],
            "status": "partial",
            "summary": "r1 结果",
            "gaps": ["仍缺官方文件"],
            "source_count": 1,
        }
    ]
