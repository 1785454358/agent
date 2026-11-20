"""Graph state and reducers for the Workflow research strategy."""

from __future__ import annotations

from typing import Annotated, TypedDict

from deeptrace.domain import CoverageAssessment, ResearchOutcome, ResearchRequirement
from deeptrace.domain.evidence import Finding
from deeptrace.domain.delivery import DeliveryPlan
from deeptrace.domain.research import ResearchTopicOutcome
from deeptrace.research import VerificationResult
from deeptrace.strategies.model_io import ResearchBranchContext
from deeptrace.strategies.source_reread import SourceReadAction
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
    research_brief: dict[str, object] | None
    delivery_plan: DeliveryPlan | None
    delivery_plan_history: list[dict]
    task_briefs: dict[str, dict[str, str]]
    supplement_targets: dict[str, list[str]]
    evidence_contract_version: int
    decomposition_degraded: bool
    evaluation_snapshot: dict | None
    coverage: CoverageAssessment | None
    source_eligibility: dict[str, str]
    diagnostic_gaps: Annotated[list[str], merge_unique_strings]

    # Workflow-internal channels.
    queries: list[str]
    recovery_attempted: bool
    recovery_queries: list[str]
    recovery_search_dispatched: bool
    reread_attempted: bool
    reread_actions: list[SourceReadAction]
    reread_queries: list[str]
    progress_before_supplement: list[str] | None
    supplement_completed: bool
    no_progress: bool
    topic_outcomes: Annotated[list[ResearchTopicOutcome], merge_topic_outcomes]
    evidence_ids: Annotated[list[str], merge_unique_strings]
    findings: list[Finding]
    executed_steps: Annotated[int, add_executed_steps]
    evaluation: WorkflowEvaluation | ReferenceWorkflowEvaluation | None
    verification: VerificationResult | None
    outcome: ResearchOutcome | None


class TopicBranchState(ResearchBranchContext):
    """Private per-query input for one Send fan-out topic branch."""

    run_id: str
    thread_id: str
    query: str
    prior_evidence_ids: list[str]
