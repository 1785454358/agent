"""Application service owning Harness State construction and graph invocation."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from deeptrace.domain import (
    ResearchMode,
    ResponseMode,
    ResponseOutcome,
    normalize_research_mode,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.state import new_conversation, new_turn


MAX_QUESTION_LENGTH = 20_000

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


class ExecutionIdentityMismatch(Exception):
    """Config thread identity does not match the request before invocation."""


class ApplicationResearchRequest(BaseModel):
    """Canonical creation request; legacy mode aliases normalize here only."""

    model_config = ConfigDict(extra="forbid")

    run_id: Identifier
    thread_id: Identifier
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH),
    ]
    mode: ResearchMode
    response_mode: ResponseMode | None = None

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: object) -> object:
        if isinstance(value, ResearchMode):
            return value
        return normalize_research_mode(str(value))


class ResearchApplicationService:
    """Single entry point that turns a request into a graph invocation."""

    def __init__(self, graph) -> None:
        self._graph = graph

    async def invoke(
        self,
        request: ApplicationResearchRequest,
        *,
        config: dict[str, Any] | None,
        context: HarnessContext,
    ):
        merged_config = dict(config or {})
        configurable = dict(merged_config.get("configurable") or {})

        config_thread_id = configurable.get("thread_id")
        if not isinstance(config_thread_id, str) or not config_thread_id.strip():
            raise ExecutionIdentityMismatch(
                "config.configurable.thread_id is required before graph invocation"
            )
        if config_thread_id != request.thread_id:
            raise ExecutionIdentityMismatch(
                "config.configurable.thread_id does not match request thread_id: "
                f"{config_thread_id!r} != {request.thread_id!r}"
            )
        if request.response_mode is not None:
            configurable["response_mode_override"] = request.response_mode
        merged_config["configurable"] = configurable

        initial_state = {
            "conversation": new_conversation(request.thread_id, request.mode),
            "turn": new_turn(request.run_id, request.question, request.mode),
        }
        result = await self._graph.ainvoke(
            initial_state, config=merged_config, context=context
        )
        turn = result["turn"]
        response_outcome = turn.get("response_outcome")
        if response_outcome is None:
            raise RuntimeError(
                "graph finished without a response outcome: "
                f"status={turn.get('status')}"
            )
        return ResponseOutcome.model_validate(response_outcome)
