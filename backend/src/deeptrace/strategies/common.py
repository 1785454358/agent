"""Shared research boundaries; strategy-specific scheduling stays in nodes."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig

from deeptrace.domain import ResearchInput, ResearchTopicInput, ResearchTopicOutcome
from deeptrace.domain.evidence import Finding
from deeptrace.harness.registry import ResearchStrategyGraph


def research_input_from_state(state: Mapping[str, Any]) -> ResearchInput:
    return ResearchInput.model_validate(
        {
            "run_id": state["run_id"],
            "thread_id": state["thread_id"],
            "question": state["question"],
            "conversation_summary": state.get("conversation_summary") or {},
            "recent_messages": state.get("recent_messages") or [],
            "prior_evidence_ids": state.get("prior_evidence_ids") or [],
            "unresolved_gaps": [],
            "budget": state.get("budget") or {},
            "current_date": state["current_date"],
            "timezone": state["timezone"],
        }
    )


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
            agent = outcome.agent_outcome
            if agent is not None and agent.status != "completed":
                return agent.stop_reason
    return reason
