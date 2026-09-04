import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from deeptrace.models import (
    SectionResult,
    TaskCompletion,
    TaskCoverage,
)
from deeptrace.orchestration.nodes import ResearchWorkflowNodes


class _FailingResearcher:
    async def adecide(self, **_kwargs):
        raise RuntimeError("provider rejected request")


def test_researcher_provider_error_becomes_task_failure(research_plan) -> None:
    task = research_plan.tasks[0]
    settings = SimpleNamespace(
        hard_max_steps=12,
        max_fetched_pages=20,
        max_cost_usd=None,
        max_runtime_seconds=600,
        max_task_rounds=3,
        input_cost_per_million=None,
        output_cost_per_million=None,
    )
    nodes = ResearchWorkflowNodes(
        planner=None,
        researcher=_FailingResearcher(),
        writer=None,
        executor=None,
        settings=settings,
        runtime=None,
    )
    state = {
        "user_query": research_plan.original_query,
        "research_plan": research_plan,
        "current_task_index": 0,
        "task_coverages": {
            task.task_id: TaskCoverage(task_id=task.task_id, status="running")
        },
        "messages": [],
        "notes": {},
        "force_finalize": False,
        "step_count": 1,
        "fetched_page_count": 0,
        "api_token_count": 0,
        "estimated_cost_usd": 0.0,
        "started_at": datetime.now(UTC).isoformat(),
        "termination_reason": "",
    }

    update = asyncio.run(nodes.research_node(state))

    assert update["pending_task_completion"].summary == "researcher_error"
    assert update["task_coverages"][task.task_id].failure_reason == (
        "researcher_error:RuntimeError"
    )
    assert update["events"][0].event_type == "task.failed"


def test_task_index_advances_on_finalize(research_plan) -> None:
    task = research_plan.tasks[0]
    settings = SimpleNamespace(
        hard_max_steps=12,
        max_fetched_pages=20,
        max_cost_usd=None,
        max_runtime_seconds=600,
        max_task_rounds=3,
        input_cost_per_million=None,
        output_cost_per_million=None,
    )
    nodes = ResearchWorkflowNodes(
        planner=None,
        researcher=None,
        writer=None,
        executor=None,
        settings=settings,
        runtime=None,
    )
    coverage = TaskCoverage(task_id=task.task_id, status="running")
    state = {
        "research_plan": research_plan,
        "current_task_index": 0,
        "task_coverages": {task.task_id: coverage},
        "pending_task_completion": TaskCompletion(
            task_id=task.task_id,
            summary="完成",
            covered_topics=task.expected_topics,
        ),
        "notes": {},
        "messages": [],
    }

    provisional = asyncio.run(nodes.complete_task_node(state))

    assert "current_task_index" not in provisional
    section = provisional["section_results"][task.task_id]

    finalized = asyncio.run(
        nodes.finalize_task_node(
            {**state, "section_results": {task.task_id: section}}
        )
    )

    assert finalized["current_task_index"] == 1
    assert (
        finalized["section_results"][task.task_id].task_id == task.task_id
    )
