"""Graph state and reducers for the Multi-Agent strategy."""

from __future__ import annotations

from typing import Annotated, TypedDict

from deeptrace.domain import ResearchOutcome
from deeptrace.domain.evidence import Finding
from deeptrace.domain.research import ResearchTopicOutcome
from deeptrace.strategies.multi_agent.models import SupervisorEvaluation


def merge_unique_strings(
    left: list[str] | None, right: list[str] | None
) -> list[str]:
    merged: list[str] = list(left or [])
    for value in right or []:
        if value not in merged:
            merged.append(value)
    return merged


def merge_topic_outcomes(
    left: list[ResearchTopicOutcome] | None,
    right: list[ResearchTopicOutcome] | None,
) -> list[ResearchTopicOutcome]:
    merged: list[ResearchTopicOutcome] = list(left or [])
    positions = {outcome.query: index for index, outcome in enumerate(merged)}
    for outcome in right or []:
        position = positions.get(outcome.query)
        if position is None:
            positions[outcome.query] = len(merged)
            merged.append(outcome)
        else:
            merged[position] = outcome
    return merged


def add_executed_steps(left: int | None, right: int | None) -> int:
    return int(left or 0) + int(right or 0)


class MultiAgentState(TypedDict, total=False):
    # Flat ResearchInput contract, matching the top-level runtime graph invocation.
    run_id: str
    thread_id: str
    question: str
    conversation_summary: dict
    prior_evidence_ids: list[str]
    unresolved_gaps: Annotated[list[str], merge_unique_strings]
    budget: dict
    current_date: str
    timezone: str

    # Loop state (all persisted at checkpoint boundaries).
    assignments: list[str]
    dispatched_queries: Annotated[list[str], merge_unique_strings]
    round_number: int
    researcher_outcomes: Annotated[list[ResearchTopicOutcome], merge_topic_outcomes]
    evidence_ids: Annotated[list[str], merge_unique_strings]
    findings: list[Finding]
    evaluation: SupervisorEvaluation | None
    executed_steps: Annotated[int, add_executed_steps]
    outcome: ResearchOutcome | None


class ResearcherBranchState(TypedDict):
    """Private per-researcher input for one Send fan-out branch."""

    run_id: str
    thread_id: str
    query: str
    researcher_index: int
    round_number: int
