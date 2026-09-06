"""Persistent LangGraph state and pure task-ledger selectors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from deeptrace.models import RunEvent, UsageBreakdown
from deeptrace.multi_agent.models import PlannedTask


class MultiAgentGraphState(TypedDict):
    """Serializable coordination state for one Multi-Agent graph run."""

    question: str
    current_date: str
    timezone: str
    tasks: dict[str, PlannedTask]
    ready_task_ids: list[str]
    next_task_number: int
    supervisor_iteration: int
    supervisor_circuit_open: bool
    first_batch: bool
    final_sufficient: bool
    final_gaps: list[str]
    termination_reason: str
    research_context: str
    final_sources: list[str]
    final_answer: str
    events: list[RunEvent]
    role_usage: UsageBreakdown
    stage_seconds: dict[str, float]
    step_count: int
    max_supervisor_iterations: int
    sources_before_batch: list[str]


def ready_task_ids(tasks: Mapping[str, PlannedTask]) -> list[str]:
    """Return pending tasks whose parent tasks have delivered a result."""
    executed = {
        task_id for task_id, task in tasks.items() if task.result is not None
    }
    return [
        task_id
        for task_id, task in tasks.items()
        if task.status == "pending"
        and set(task.assignment.parent_ids) <= executed
    ]


def open_leaf_tasks(tasks: Mapping[str, PlannedTask]) -> list[PlannedTask]:
    """Return unresolved terminal tasks not superseded by an executed child."""
    superseded = {
        parent_id
        for task in tasks.values()
        if task.result is not None
        for parent_id in task.assignment.parent_ids
    }
    return [
        task
        for task_id, task in tasks.items()
        if task_id not in superseded
        and task.status in {"partial", "blocked"}
        and task.result is not None
        and bool(task.result.gaps)
    ]


def leaf_gaps(tasks: Mapping[str, PlannedTask]) -> list[str]:
    """Return stable, de-duplicated gaps from current plan leaves."""
    gaps: list[str] = []
    for task in open_leaf_tasks(tasks):
        assert task.result is not None
        for gap in task.result.gaps:
            if gap not in gaps:
                gaps.append(gap)
                if len(gaps) == 6:
                    return gaps
    return gaps


def compact_task_history(tasks: Mapping[str, PlannedTask]) -> list[dict]:
    """Build the bounded coordination view sent to the Supervisor."""
    history: list[dict] = []
    for task in tasks.values():
        assignment = task.assignment
        result = task.result
        history.append(
            {
                "id": assignment.id,
                "objective": assignment.objective,
                "required_outputs": list(assignment.required_outputs),
                "excluded_scope": list(assignment.excluded_scope),
                "source_guidance": list(assignment.source_guidance),
                "parent_ids": list(assignment.parent_ids),
                "status": task.status,
                "summary": result.summary if result is not None else "",
                "gaps": list(result.gaps) if result is not None else [],
                "source_count": len(result.source_urls) if result is not None else 0,
            }
        )
    return history
