from datetime import date

import pytest
from pydantic import ValidationError

from deeptrace.models import ResearchPlan, ResearchTask, ResearchTimeRange, RunEvent


def test_research_plan_accepts_bounded_serializable_tasks() -> None:
    task = ResearchTask(
        task_id="task-01",
        section_id="section-01",
        title="技术进展",
        question="2024 年有哪些关键技术进展？",
        planned_queries=["2024 AI Agent 技术进展"],
        expected_topics=["规划", "工具调用"],
        min_sources=2,
    )
    plan = ResearchPlan(
        plan_id="plan-abc",
        original_query="2024年 AI Agent 进展",
        normalized_query="2024年 AI Agent 进展",
        objective="总结年度进展",
        language="zh-CN",
        time_range=ResearchTimeRange(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            description="2024 年",
        ),
        tasks=[
            task,
            task.model_copy(
                update={
                    "task_id": "task-02",
                    "section_id": "section-02",
                    "title": "应用进展",
                }
            ),
        ],
        report_outline=["技术进展", "应用进展"],
    )

    assert plan.model_dump(mode="json")["time_range"]["start_date"] == "2024-01-01"


def test_research_plan_rejects_more_than_five_tasks() -> None:
    task = ResearchTask(
        task_id="task-01",
        section_id="section-01",
        title="主题",
        question="问题",
        planned_queries=["查询"],
        expected_topics=["主题"],
        min_sources=2,
    )

    with pytest.raises(ValidationError):
        ResearchPlan(
            plan_id="plan",
            original_query="问题",
            normalized_query="问题",
            objective="目标",
            language="zh-CN",
            tasks=[task] * 6,
            report_outline=["主题"],
        )


def test_run_event_details_are_not_shared() -> None:
    first = RunEvent(event_type="planning.started", message="开始")
    second = RunEvent(event_type="planning.started", message="开始")

    first.details["count"] = 1

    assert second.details == {}
