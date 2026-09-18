"""Serializable state shared by the loop and its policies."""

from enum import StrEnum
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from deeptrace.domain import (
    ErrorRecord,
    ResearchTopicInput,
    ResearchTopicOutcome,
    TopicStepError,
)

MAX_TODOS = 20
MAX_TODO_CONTENT_CHARS = 500


class TodoStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class AgentTodo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_TODO_CONTENT_CHARS)
    status: TodoStatus = TodoStatus.PENDING


class WriteTodosArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    todos: list[AgentTodo] = Field(min_length=1, max_length=MAX_TODOS)


def _merge_unique(left: list[str] | None, right: list[str] | None) -> list[str]:
    merged = list(left or [])
    for value in right or []:
        if value not in merged:
            merged.append(value)
    return merged


def _merge_errors(
    left: list[TopicStepError] | None, right: list[TopicStepError] | None
) -> list[TopicStepError]:
    return list(left or []) + list(right or [])


def _add_steps(left: int | None, right: int | None) -> int:
    return int(left or 0) + int(right or 0)


class AgentExecutorState(TypedDict, total=False):
    topic_input: ResearchTopicInput
    messages: Annotated[list[Any], add_messages]
    model_messages: list[Any]
    iteration: int
    consecutive_errors: int
    completion_nudges: int
    todos: list[AgentTodo]
    evidence_ids: Annotated[list[str], _merge_unique]
    attempted_urls: Annotated[list[str], _merge_unique]
    seen_urls: list[str]
    errors: Annotated[list[TopicStepError], _merge_errors]
    failures: list[ErrorRecord]
    executed_steps: Annotated[int, _add_steps]
    pages_fetched: int
    stop_reason: str
    outcome: ResearchTopicOutcome


def topic_input(state: AgentExecutorState) -> ResearchTopicInput:
    return ResearchTopicInput.model_validate(state["topic_input"])
