"""Graph state and reducers for the Workflow research strategy."""

from __future__ import annotations

from typing import Annotated, TypedDict

from deeptrace.domain import CoverageAssessment, ResearchOutcome, ResearchRequirement
from deeptrace.domain.evidence import Finding
from deeptrace.domain.research import ResearchTopicOutcome
from deeptrace.strategies.workflow.models import (
    ReferenceWorkflowEvaluation,
    WorkflowEvaluation,
)


def merge_unique_strings(left: list[str] | None, right: list[str] | None) -> list[str]:
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


class WorkflowState(TypedDict, total=False):
    # Flat ResearchInput contract, matching the top-level runtime graph invocation.
    run_id: str
    thread_id: str
    question: str
    conversation_summary: dict
    recent_messages: list[str]
    prior_evidence_ids: list[str]
    unresolved_gaps: list[str]
    budget: dict
    current_date: str
    timezone: str
    requirements: list[ResearchRequirement]
    target_requirement_ids: list[str]
    query_targets: dict[str, list[str]]
    supplement_targets: dict[str, list[str]]
    evidence_contract_version: int
    decomposition_degraded: bool
    coverage: CoverageAssessment | None
    source_eligibility: dict[str, str]
    diagnostic_gaps: Annotated[list[str], merge_unique_strings]

    # Workflow-internal channels.
    queries: list[str]
    topic_outcomes: Annotated[list[ResearchTopicOutcome], merge_topic_outcomes]
    evidence_ids: Annotated[list[str], merge_unique_strings]
    findings: list[Finding]
    executed_steps: Annotated[int, add_executed_steps]
    evaluation: WorkflowEvaluation | ReferenceWorkflowEvaluation | None
    outcome: ResearchOutcome | None


class TopicBranchState(TypedDict):
    """Private per-query input for one Send fan-out topic branch."""

    run_id: str
    thread_id: str
    query: str
    original_task: str
    constraints: list[str]
    context_notes: list[str]
    requirements: list[ResearchRequirement]
    evidence_contract_version: int
    target_requirement_ids: list[str]
    research_gaps: list[str]
    prior_evidence_ids: list[str]
