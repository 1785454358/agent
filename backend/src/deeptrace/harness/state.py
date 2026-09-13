from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, TypedDict, cast

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from deeptrace.domain import (
    BudgetSnapshot,
    ConversationIntent,
    ConversationSummary,
    ErrorRecord,
    ExecutionStatus,
    Finding,
    ResearchInput,
    ResearchOutcome,
    ResearchMode,
    ResponseOutcome,
    ResponseMode,
)


class ConversationState(TypedDict):
    thread_id: str
    messages: list[AnyMessage]
    summary: ConversationSummary
    active_mode: ResearchMode
    user_memory_refs: list[str]
    workspace_memory_refs: list[str]
    evidence_ids: list[str]
    established_findings: list[Finding]
    unresolved_gaps: list[str]
    created_at: str
    updated_at: str
    state_version: int


class ConversationUpdate(TypedDict, total=False):
    thread_id: str
    messages: list[AnyMessage]
    summary: ConversationSummary
    active_mode: ResearchMode
    user_memory_refs: list[str]
    workspace_memory_refs: list[str]
    evidence_ids: list[str]
    established_findings: list[Finding]
    unresolved_gaps: list[str]
    created_at: str
    updated_at: str
    state_version: int


_CONVERSATION_UPDATE_FIELDS = frozenset(
    {
        "thread_id",
        "messages",
        "summary",
        "active_mode",
        "user_memory_refs",
        "workspace_memory_refs",
        "evidence_ids",
        "established_findings",
        "unresolved_gaps",
        "created_at",
        "updated_at",
        "state_version",
    }
)


class TurnState(TypedDict):
    run_id: str
    user_input: str
    intent: ConversationIntent
    selected_mode: ResearchMode
    response_mode: ResponseMode
    requires_research: bool
    research_request: ResearchInput | None
    research_outcome: ResearchOutcome | None
    response_outcome: ResponseOutcome | None
    recalled_memory_ids: list[str]
    recalled_memories: list[dict[str, str]]
    active_evidence_ids: list[str]
    budget: BudgetSnapshot
    status: ExecutionStatus
    error: ErrorRecord | None


def merge_conversation(
    left: ConversationState, right: ConversationUpdate
) -> ConversationState:
    unknown_fields = set(right) - _CONVERSATION_UPDATE_FIELDS
    if unknown_fields:
        names = ", ".join(sorted(unknown_fields))
        raise ValueError(f"unknown conversation fields: {names}")

    merged = dict(left)
    if "messages" in right:
        merged["messages"] = list(
            add_messages(left.get("messages", []), right["messages"])
        )
    merged.update({key: value for key, value in right.items() if key != "messages"})
    return cast(ConversationState, merged)


class HarnessState(TypedDict):
    conversation: Annotated[ConversationState, merge_conversation]
    turn: TurnState


def new_conversation(
    thread_id: str, mode: ResearchMode
) -> ConversationState:
    now = datetime.now(UTC).isoformat()
    return {
        "thread_id": thread_id,
        "messages": [],
        "summary": ConversationSummary(),
        "active_mode": mode,
        "user_memory_refs": [],
        "workspace_memory_refs": [],
        "evidence_ids": [],
        "established_findings": [],
        "unresolved_gaps": [],
        "created_at": now,
        "updated_at": now,
        "state_version": 1,
    }


def new_turn(run_id: str, user_input: str, mode: ResearchMode) -> TurnState:
    return {
        "run_id": run_id,
        "user_input": user_input,
        "intent": ConversationIntent.RESEARCH,
        "selected_mode": mode,
        "response_mode": ResponseMode.ANSWER,
        "requires_research": True,
        "research_request": None,
        "research_outcome": None,
        "response_outcome": None,
        "recalled_memory_ids": [],
        "recalled_memories": [],
        "active_evidence_ids": [],
        "budget": BudgetSnapshot(),
        "status": ExecutionStatus.PENDING,
        "error": None,
    }
