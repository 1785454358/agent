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


def leaf_gap_records(
    tasks: Mapping[str, PlannedTask],
) -> list[tuple[str, str]]:
    """Return unresolved ``(task_id, gap)`` pairs not covered by a child."""
    covered = {
        (parent_id, required_output)
        for task in tasks.values()
        if task.result is not None
        for parent_id in task.assignment.parent_ids
        for required_output in task.assignment.required_outputs
    }
    records: list[tuple[str, str]] = []
    for task_id, task in tasks.items():
        if (
            task.status not in {"partial", "blocked"}
            or task.result is None
        ):
            continue
        for gap in task.result.gaps:
            if (task_id, gap) not in covered:
                records.append((task_id, gap))
    return records


def open_leaf_tasks(tasks: Mapping[str, PlannedTask]) -> list[PlannedTask]:
    """Return terminal tasks with at least one uncovered gap."""
    open_task_ids = {task_id for task_id, _ in leaf_gap_records(tasks)}
    return [
        task
        for task_id, task in tasks.items()
        if task_id in open_task_ids
    ]


def leaf_gaps(tasks: Mapping[str, PlannedTask]) -> list[str]:
    """Return stable, de-duplicated gaps from current plan leaves."""
    gaps: list[str] = []
    for _, gap in leaf_gap_records(tasks):
        if gap not in gaps:
            gaps.append(gap)
            if len(gaps) == 6:
                return gaps
    return gaps


def task_source_urls(tasks: Mapping[str, PlannedTask]) -> set[str]:
    """Return every source URL actually read by terminal tasks."""
    return {
        url
        for task in tasks.values()
        if task.result is not None
        for url in task.result.source_urls
    }


def _route_ready_work(state: Mapping) -> str:
    if state.get("termination_reason"):
        return "writer"
    return "execute" if state.get("ready_task_ids") else "writer"


def route_after_plan(state: Mapping) -> str:
    """Route a planned graph run to execution only with executable work."""
    return _route_ready_work(state)


def route_after_replan(state: Mapping) -> str:
    """Route a reviewed graph run to its next batch or final writing."""
    return _route_ready_work(state)


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
