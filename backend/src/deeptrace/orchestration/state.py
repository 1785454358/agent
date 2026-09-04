"""LangGraph state for the three-stage Basic research pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from deeptrace.models import (
    RawDocument,
    RunEvent,
    TokenUsage,
    UsageBreakdown,
    add_token_usages,
)


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Merge immutable node updates; ``None`` removes an existing key."""
    merged = dict(left)
    for key, value in right.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def merge_token_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
    """Add Provider counters without mutating either reducer input."""
    return add_token_usages(left, right)


def merge_usage_breakdown(
    left: UsageBreakdown, right: UsageBreakdown
) -> UsageBreakdown:
    """Add the Planner and Writer role totals."""
    return UsageBreakdown(
        planner=add_token_usages(left.planner, right.planner),
        writer=add_token_usages(left.writer, right.writer),
    )


def merge_stage_seconds(
    left: dict[str, float], right: dict[str, float]
) -> dict[str, float]:
    """Accumulate elapsed seconds reported by each graph stage."""
    merged = dict(left)
    for stage, seconds in right.items():
        merged[stage] = merged.get(stage, 0.0) + seconds
    return merged


class GraphState(TypedDict):
    """Serializable runtime state; embedding vectors remain process-local."""

    user_query: str
    search_queries: list[str]
    initial_search: dict[str, Any] | None
    documents: Annotated[dict[str, RawDocument], merge_dicts]
    research_context: str
    final_sources: list[str]
    events: Annotated[list[RunEvent], operator.add]
    started_at: str
    fetched_page_count: Annotated[int, operator.add]
    api_token_count: Annotated[int, operator.add]
    estimated_cost_usd: Annotated[float, operator.add]
    provider_usage: Annotated[TokenUsage, merge_token_usage]
    role_usage: Annotated[UsageBreakdown, merge_usage_breakdown]
    stage_seconds: Annotated[dict[str, float], merge_stage_seconds]
    step_count: Annotated[int, operator.add]
    force_finalize: bool
    final_answer: str
    termination_reason: str
