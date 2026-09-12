"""Graph state and reducers for the research topic subgraph."""

from __future__ import annotations

from typing import Annotated, TypedDict

from deeptrace.domain import (
    ResearchMode,
    ResearchTopicInput,
    ResearchTopicOutcome,
    ToolResult,
    TopicStepError,
)


def merge_unique_evidence_ids(
    left: list[str] | None, right: list[str] | None
) -> list[str]:
    merged: list[str] = list(left or [])
    for value in right or []:
        if value not in merged:
            merged.append(value)
    return merged


def merge_unique_urls(
    left: list[str] | None, right: list[str] | None
) -> list[str]:
    return merge_unique_evidence_ids(left, right)


def merge_topic_errors(
    left: list[TopicStepError] | None, right: list[TopicStepError] | None
) -> list[TopicStepError]:
    return list(left or []) + list(right or [])


def add_executed_steps(left: int | None, right: int | None) -> int:
    return int(left or 0) + int(right or 0)


class ResearchTopicState(TypedDict, total=False):
    topic_input: ResearchTopicInput
    search_result: ToolResult
    selected_urls: list[str]
    evidence_ids: Annotated[list[str], merge_unique_evidence_ids]
    attempted_urls: Annotated[list[str], merge_unique_urls]
    errors: Annotated[list[TopicStepError], merge_topic_errors]
    executed_steps: Annotated[int, add_executed_steps]
    outcome: ResearchTopicOutcome | None


class FetchBranchState(TypedDict):
    """Private per-URL input for one Send fan-out fetch branch."""

    run_id: str
    thread_id: str
    query: str
    url: str
    ordinal: int
    mode: ResearchMode
    caller_id: str
