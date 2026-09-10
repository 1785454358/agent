from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deeptrace.domain import (
    ExecutionStatus,
    ResearchInput,
    ResearchOutcome,
    ResearchProfile,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.registry import ProfileRegistry
from deeptrace.harness.state import HarnessState


def _route_profile(state: HarnessState) -> str:
    return state["turn"]["selected_profile"].value


def _research_input(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> ResearchInput:
    conversation = state["conversation"]
    turn = state["turn"]
    now = runtime.context.clock.now()
    return ResearchInput(
        question=turn["user_input"],
        conversation_summary=conversation["summary"],
        prior_evidence_ids=conversation["evidence_ids"],
        unresolved_gaps=conversation["unresolved_gaps"],
        budget=turn["budget"],
        current_date=now.date().isoformat(),
        timezone=str(now.tzinfo),
    )


def _profile_node(registry: ProfileRegistry, profile: ResearchProfile):
    async def invoke_profile(
        state: HarnessState,
        runtime: Runtime[HarnessContext],
        config: RunnableConfig,
    ) -> dict[str, Any]:
        registration = registry.resolve(profile)
        request = _research_input(state, runtime)
        raw = await registration.graph.ainvoke(
            request.model_dump(mode="json"), config=config
        )
        outcome = ResearchOutcome.model_validate(raw)
        if outcome.profile is not profile:
            raise ValueError(
                "outcome profile does not match routed profile: "
                f"expected {profile.value}, got {outcome.profile.value}"
            )
        turn = dict(state["turn"])
        turn["research_request"] = request
        turn["research_outcome"] = outcome
        turn["active_evidence_ids"] = list(outcome.evidence_ids)
        conversation = state["conversation"]
        return {
            "turn": turn,
            "conversation": {
                "active_profile": profile,
                "evidence_ids": list(
                    dict.fromkeys(
                        conversation["evidence_ids"] + outcome.evidence_ids
                    )
                ),
                "established_findings": (
                    conversation["established_findings"] + outcome.findings
                ),
                "unresolved_gaps": list(outcome.unresolved_gaps),
            },
        }

    return invoke_profile


def _initialize_turn(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    turn["status"] = ExecutionStatus.RUNNING
    return {"turn": turn}


def _finalize_turn(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    outcome = turn["research_outcome"]
    turn["status"] = (
        ExecutionStatus.COMPLETED
        if outcome is not None and outcome.termination_reason == "completed"
        else ExecutionStatus.PARTIAL
    )
    return {"turn": turn}


def build_harness_graph(registry: ProfileRegistry, checkpointer=None):
    builder = StateGraph(HarnessState, context_schema=HarnessContext)
    builder.add_node("initialize_turn", _initialize_turn)
    for profile in ResearchProfile:
        builder.add_node(profile.value, _profile_node(registry, profile))
        builder.add_edge(profile.value, "finalize_turn")
    builder.add_node("finalize_turn", _finalize_turn)
    builder.add_edge(START, "initialize_turn")
    builder.add_conditional_edges(
        "initialize_turn",
        _route_profile,
        {profile.value: profile.value for profile in ResearchProfile},
    )
    builder.add_edge("finalize_turn", END)
    return builder.compile(checkpointer=checkpointer)
