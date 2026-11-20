"""Checkpointed planning, collection, coverage review and delivery channels."""

from typing import Annotated, TypedDict

from deeptrace.domain import ResearchOutcome, ResearchRequirement, ResearchTopicOutcome
from deeptrace.strategies.workflow.state import (
    add_executed_steps,
    merge_topic_outcomes,
    merge_unique_strings,
)


class ControllerState(TypedDict, total=False):
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
    delivery_first: bool
    requirements: list[ResearchRequirement]
    query_targets: dict
    research_brief: dict | None
    task_briefs: dict
    decomposition_degraded: bool
    queries: list[str]
    active_queries: list[str]
    active_query: str
    coverage_review: str | None
    first_round_missing: list[str]
    supplement_targets: dict[str, list[str]]
    supplement_gaps: dict[str, list[str]]
    topic_outcomes: Annotated[list[ResearchTopicOutcome], merge_topic_outcomes]
    evidence_ids: Annotated[list[str], merge_unique_strings]
    executed_steps: Annotated[int, add_executed_steps]
    outcome: ResearchOutcome
