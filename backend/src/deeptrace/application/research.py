"""Application service owning Harness State construction and graph invocation."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from deeptrace.application.result import ApplicationRunResult
from deeptrace.domain import (
    ResearchMode,
    ResearchOutcome,
    ResponseMode,
    ResponseOutcome,
)
from deeptrace.domain.run import TERMINAL_STATUSES, ResearchSufficiency
from deeptrace.domain.execution import ResearchModeSelection, normalize_mode_selection
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.state import new_conversation, new_turn
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from deeptrace.observability.langsmith import application_inputs, application_outputs

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
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH
        ),
    ]
    mode: ResearchModeSelection = "auto"
    response_mode: ResponseMode | None = None

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: object) -> object:
        if isinstance(value, ResearchMode):
            return value
        return normalize_mode_selection(str(value))


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
    ) -> ApplicationRunResult:
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

        return await self._invoke_graph(request, merged_config, context,
            langsmith_extra={"metadata": {"run_id": request.run_id,
                "thread_id": request.thread_id, "mode": str(request.mode)}})

    @traceable(name="research.run", run_type="chain",
               process_inputs=application_inputs, process_outputs=application_outputs)
    async def _invoke_graph(self, request, merged_config, context):
        turn = new_turn(request.run_id, request.question, request.mode)
        aget_state = getattr(self._graph, "aget_state", None)
        snapshot = None
        if aget_state is not None:
            try:
                snapshot = await aget_state(merged_config)
            except ValueError:
                snapshot = None  # no checkpointer: always a fresh conversation

        if snapshot is not None and snapshot.next:
            # Interrupted run for THIS run_id: resume from the durable
            # checkpoint instead of starting over (LangGraph resume semantics).
            prior_turn = snapshot.values.get("turn") or {}
            if prior_turn.get("run_id") == request.run_id:
                if prior_turn.get("research_flow_version") != 2:
                    raise ValueError(
                        "legacy_research_checkpoint_requires_original_runtime: "
                        "use the saved original runtime to resume, or start a new run"
                    )
                if (tree := get_current_run_tree()) is not None:
                    tree.add_metadata({"resumed": True, "checkpoint_id": (
                        (getattr(snapshot, "config", None) or {}).get("configurable") or {}
                    ).get("checkpoint_id")})
                result = await self._graph.ainvoke(
                    None, config=merged_config, context=context
                )
                return await self._extract_result(result, request, context)

        if snapshot is not None and snapshot.values.get("conversation"):
            # Multi-turn continuation: keep the persisted ConversationState.
            initial_state: dict[str, Any] = {"turn": turn}
        else:
            initial_state = {
                "conversation": new_conversation(request.thread_id, turn["selected_mode"]),
                "turn": turn,
            }
        result = await self._graph.ainvoke(
            initial_state, config=merged_config, context=context
        )
        return await self._extract_result(result, request, context)

    @staticmethod
    async def _extract_result(
        result: dict[str, Any],
        request: ApplicationResearchRequest,
        context: HarnessContext,
    ) -> ApplicationRunResult:
        turn = result["turn"]
        status = turn.get("status")
        if status not in TERMINAL_STATUSES:
            raise RuntimeError(f"graph finished without a terminal status: {status}")
        response_outcome = turn.get("response_outcome")
        if response_outcome is None and status in {"completed", "partial"}:
            raise RuntimeError(
                "graph finished without a response outcome: "
                f"status={turn.get('status')}"
            )
        response = (
            ResponseOutcome.model_validate(response_outcome)
            if response_outcome is not None else None
        )
        raw_research = turn.get("research_outcome")
        research = (
            ResearchOutcome.model_validate(raw_research)
            if raw_research is not None
            else None
        )
        reason = response.partial_reason if response is not None else None
        if research is not None and not research.delivery_first and research.termination_reason != "completed":
            reason = research.termination_reason
        gaps = list(research.unresolved_gaps) if research is not None else []
        if (
            status == "completed"
            and research is not None
            and research.mode == ResearchMode.WORKFLOW
            and not research.delivery_first
        ):
            reason = "workflow_completed"
            if response is not None and response.partial_reason:
                gaps = list(dict.fromkeys([*gaps, f"response:{response.partial_reason}"]))
        sources: list[str] = []
        if response is not None and response.cited_evidence_ids:
            evidence = await context.evidence_store.get_many(
                context.workspace_id, response.cited_evidence_ids
            )
            sources = [item.canonical_url for item in evidence]
        return ApplicationRunResult(
            run_id=request.run_id,
            thread_id=request.thread_id,
            status=status,
            response_outcome=response,
            research_outcome=research,
            termination_reason=reason or (
                "runtime_error" if status == "failed" else status
            ),
            executed_steps=research.executed_steps if research is not None else 0,
            unresolved_gaps=gaps,
            sources=sources,
            research_sufficiency=_research_sufficiency(research, turn),
        )


def _research_sufficiency(
    research: ResearchOutcome | None, turn: dict[str, Any]
) -> ResearchSufficiency:
    """Use validated research coverage, never the scheduler's completion flag."""
    if research is None:
        if not turn.get("requires_research", True):
            return ResearchSufficiency.NOT_REQUIRED
        return ResearchSufficiency.UNKNOWN
    if not research.delivery_first and research.evidence_contract_version in (2, 3):
        from deeptrace.strategies.evidence_evaluation import coverage_complete

        if coverage_complete(research.model_dump()):
            return ResearchSufficiency.SUFFICIENT
        if research.coverage is not None:
            return ResearchSufficiency.INSUFFICIENT
    if research.unresolved_gaps or research.termination_reason in {
        "insufficient_evidence", "no_sources",
    }:
        return ResearchSufficiency.INSUFFICIENT
    return ResearchSufficiency.UNKNOWN
