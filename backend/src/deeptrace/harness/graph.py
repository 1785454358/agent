from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deeptrace.domain import (
    ExecutionStatus,
    ResearchInput,
    ResearchOutcome,
    ResearchMode,
    ResponseInput,
    ResponseMode,
    ResponseOutcome,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.registry import ResponseGraphRegistry, StrategyRegistry
from deeptrace.harness.state import HarnessState
from deeptrace.responses.citations import select_response_mode


def _route_mode(state: HarnessState) -> str:
    return state["turn"]["selected_mode"].value


def _research_input(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> ResearchInput:
    conversation = state["conversation"]
    turn = state["turn"]
    now = runtime.context.clock.now()
    return ResearchInput(
        run_id=turn["run_id"],
        thread_id=conversation["thread_id"],
        question=turn["user_input"],
        conversation_summary=conversation["summary"],
        prior_evidence_ids=conversation["evidence_ids"],
        unresolved_gaps=conversation["unresolved_gaps"],
        budget=turn["budget"],
        current_date=now.date().isoformat(),
        timezone=str(now.tzinfo),
    )


def _mode_node(registry: StrategyRegistry, mode: ResearchMode):
    async def invoke_mode(
        state: HarnessState,
        runtime: Runtime[HarnessContext],
        config: RunnableConfig,
    ) -> dict[str, Any]:
        registration = registry.resolve(mode)
        request = _research_input(state, runtime)
        raw = await registration.graph.ainvoke(
            request.model_dump(mode="json"), config=config
        )
        outcome = ResearchOutcome.model_validate(raw["outcome"])
        if outcome.mode is not mode:
            raise ValueError(
                "outcome mode does not match routed mode: "
                f"expected {mode.value}, got {outcome.mode.value}"
            )
        turn = dict(state["turn"])
        turn["research_request"] = request
        turn["research_outcome"] = outcome
        turn["active_evidence_ids"] = list(outcome.evidence_ids)
        conversation = state["conversation"]
        return {
            "turn": turn,
            "conversation": {
                "active_mode": mode,
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

    return invoke_mode


def _initialize_turn(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    turn["status"] = ExecutionStatus.RUNNING
    return {"turn": turn}


def _select_response_mode(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    turn["response_mode"] = select_response_mode(turn["user_input"])
    return {"turn": turn}


def _route_response(state: HarnessState) -> str:
    turn = state["turn"]
    if turn["research_outcome"] is None:
        return "finalize_turn"
    return turn["response_mode"].value


def _response_node(response_registry: ResponseGraphRegistry, mode: ResponseMode):
    async def invoke_response(
        state: HarnessState,
        runtime: Runtime[HarnessContext],
        config: RunnableConfig,
    ) -> dict[str, Any]:
        registration = response_registry.resolve(mode)
        turn = state["turn"]
        response_input = ResponseInput(
            question=turn["user_input"],
            response_mode=mode,
            research_outcome=turn["research_outcome"],
            active_evidence_ids=list(turn["active_evidence_ids"]),
        )
        raw = await registration.graph.ainvoke(
            {"response_input": response_input}, config=config
        )
        outcome = ResponseOutcome.model_validate(raw["outcome"])
        if outcome.response_mode is not mode:
            raise ValueError(
                "outcome response_mode does not match routed response mode: "
                f"expected {mode.value}, got {outcome.response_mode.value}"
            )
        turn = dict(state["turn"])
        turn["response_outcome"] = outcome
        return {"turn": turn}

    return invoke_response


def _finalize_turn(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    research = turn["research_outcome"]
    response = turn["response_outcome"]
    research_usable = (
        research is not None and research.termination_reason == "completed"
    )
    response_usable = response is not None and response.partial_reason is None
    if research_usable and response_usable:
        turn["status"] = ExecutionStatus.COMPLETED
    else:
        turn["status"] = ExecutionStatus.PARTIAL
    return {"turn": turn}


def build_agent_runtime_graph(
    registry: StrategyRegistry,
    response_registry: ResponseGraphRegistry,
    checkpointer=None,
):
    builder = StateGraph(HarnessState, context_schema=HarnessContext)
    builder.add_node("initialize_turn", _initialize_turn)
    for mode in ResearchMode:
        builder.add_node(mode.value, _mode_node(registry, mode))
        builder.add_edge(mode.value, "select_response_mode")
    builder.add_node("select_response_mode", _select_response_mode)
    for mode in ResponseMode:
        builder.add_node(mode.value, _response_node(response_registry, mode))
        builder.add_edge(mode.value, "finalize_turn")
    builder.add_node("finalize_turn", _finalize_turn)
    builder.add_edge(START, "initialize_turn")
    builder.add_conditional_edges(
        "initialize_turn",
        _route_mode,
        {mode.value: mode.value for mode in ResearchMode},
    )
    builder.add_conditional_edges(
        "select_response_mode",
        _route_response,
        {
            **{mode.value: mode.value for mode in ResponseMode},
            "finalize_turn": "finalize_turn",
        },
    )
    builder.add_edge("finalize_turn", END)
    return builder.compile(checkpointer=checkpointer)
