"""Shared research boundaries; strategy-specific scheduling stays in nodes."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig

from deeptrace.domain import (
    ErrorCategory,
    EvidenceLifecycleStatus,
    ResearchInput,
    ResearchTopicInput,
    ResearchTopicOutcome,
)
from deeptrace.domain.evidence import Finding
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.registry import ResearchStrategyGraph
from deeptrace.strategies.model_io import branch_context, parent_evidence_candidates


def research_input_from_state(state: Mapping[str, Any]) -> ResearchInput:
    return ResearchInput.model_validate(
        {
            "run_id": state["run_id"],
            "thread_id": state["thread_id"],
            "question": state["question"],
            "conversation_summary": state.get("conversation_summary") or {},
            "recent_messages": state.get("recent_messages") or [],
            "prior_evidence_ids": state.get("prior_evidence_ids") or [],
            "unresolved_gaps": state.get("unresolved_gaps") or [],
            "budget": state.get("budget") or {},
            "current_date": state["current_date"],
            "timezone": state["timezone"],
        }
    )


async def validated_branch_context(
    state: Mapping[str, Any], context: HarnessContext
) -> dict[str, Any]:
    """Revalidate parent candidates before issuing a bounded current-source grant."""
    candidates = parent_evidence_candidates(state)
    try:
        records = await context.evidence_store.get_many(
            context.workspace_id, candidates
        )
    except KeyError:
        # A removed/missing parent must not invalidate all remaining sources.
        records = []
        for evidence_id in candidates:
            try:
                records.append(
                    await context.evidence_store.get(context.workspace_id, evidence_id)
                )
            except KeyError:
                continue
    authorized = [
        record.id
        for record in records
        if record.status is EvidenceLifecycleStatus.ACTIVE
    ]
    return {**branch_context(state), "authorized_evidence_ids": authorized}


async def invoke_research_branch(
    graph: ResearchStrategyGraph,
    request: ResearchTopicInput,
    config: RunnableConfig | None,
) -> ResearchTopicOutcome:
    raw = await graph.ainvoke({"topic_input": request}, config=config)
    outcome = ResearchTopicOutcome.model_validate(raw["outcome"])
    if outcome.agent_outcome and outcome.agent_outcome.status == "cancelled":
        raise asyncio.CancelledError()
    return outcome


def filter_findings(
    findings: list[Finding],
    *,
    allowed_evidence_ids: set[str],
) -> list[Finding]:
    return [
        f
        for f in findings
        if f.evidence_ids and set(f.evidence_ids) <= allowed_evidence_ids
    ]


def topic_error_gaps(outcome: ResearchTopicOutcome) -> list[str]:
    agent = outcome.agent_outcome
    extra = (
        [f"agent_exit:{agent.stop_reason}"]
        if agent and agent.status != "completed"
        else []
    )
    return extra + [
        f"topic[{outcome.query}] {error.stage}:{error.target}:{error.code}"
        for error in outcome.errors
    ]


def effective_termination_reason(
    reason: str,
    outcomes: Sequence[ResearchTopicOutcome],
) -> str:
    if reason == "completed":
        for outcome in outcomes:
            controlled = _controlled_exit(outcome)
            if controlled:
                return controlled
    return reason


def _controlled_exit(outcome: ResearchTopicOutcome) -> str | None:
    agent = outcome.agent_outcome
    if agent is None or agent.status == "completed":
        return None
    # The agent cannot complete without sources, even when no todo is open.
    # That recoverable discovery failure is not an unfinished plan/fatal exit.
    if (
        agent.stop_reason == "incomplete_plan"
        and not agent.evidence_ids
        and not agent.unfinished_todos
        and not outcome.unfinished_todos
        and agent.plan_completed >= agent.plan_total
        and outcome.plan_completed >= outcome.plan_total
        and not any(
            error.category in {ErrorCategory.FATAL, ErrorCategory.CANCELLED}
            for error in agent.errors
        )
    ):
        return None
    return agent.stop_reason


def strong_exit_reason(state: Mapping[str, Any]) -> str | None:
    """A successful sibling must not erase a controlled exit or unfinished todo."""
    from deeptrace.domain import INCOMPLETE_PLAN_REASON, unfinished_plan_items

    outcomes = [
        *(state.get("topic_outcomes") or []),
        *(state.get("researcher_outcomes") or []),
    ]
    for outcome in outcomes:
        controlled = _controlled_exit(outcome)
        if controlled:
            return controlled
    if unfinished_plan_items(outcomes):
        return INCOMPLETE_PLAN_REASON
    return None
