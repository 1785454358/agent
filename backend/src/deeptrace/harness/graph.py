from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deeptrace.domain import (
    ConversationIntent,
    ConversationSummary,
    ExecutionStatus,
    ResearchInput,
    ResearchMode,
    ResearchOutcome,
    ResponseInput,
    ResponseMode,
    ResponseOutcome,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.prompts import task_messages
from deeptrace.harness.memory.lifecycle import _recall_memory, _memory_update_node, _consolidate_memory
from deeptrace.harness.policies.context import (
    SUMMARY_FACT_LIMIT,
    SUMMARY_LIST_LIMIT,
    merge_summaries,
    plan_context_window,
)
from deeptrace.harness.policies.intent import (
    classify_intent,
    response_mode_for_intent,
)
from deeptrace.harness.registry import ResponseGraphRegistry, StrategyRegistry
from deeptrace.harness.state import HarnessState
from deeptrace.responses.citations import select_response_mode

SUMMARIZER_ROLE = "summarizer"

_MODE_PATTERN = re.compile(
    r"(workflow|plan.?execute|multi.?agent|多智能体)", re.IGNORECASE
)


def _route_mode(state: HarnessState) -> str:
    return state["turn"]["selected_mode"].value


def _summary_with_memories(
    conversation: dict[str, Any], turn: dict[str, Any]
):
    """Recalled memories are injected into a COPY of the conversation summary."""
    from deeptrace.domain import ConversationSummary

    summary = conversation["summary"]
    memories = turn.get("recalled_memories") or []
    if not memories:
        return summary
    preferences = [
        memory["content"]
        for memory in memories
        if memory.get("type") == "preference"
    ]
    facts = [
        memory["content"]
        for memory in memories
        if memory.get("type") in {"fact", "evidence"}
    ]
    return merge_summaries(
        summary,
        ConversationSummary(
            user_constraints=preferences[:SUMMARY_LIST_LIMIT],
            established_facts=facts[:SUMMARY_FACT_LIMIT],
        ),
    )


def _research_input(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> ResearchInput:
    conversation = state["conversation"]
    turn = state["turn"]
    now = runtime.context.clock.now()
    recent = [
        str(message.content)[:400]
        for message in conversation["messages"][-8:]
        if str(message.content).strip()
    ][-8:]
    return ResearchInput(
        run_id=turn["run_id"],
        thread_id=conversation["thread_id"],
        question=turn["user_input"],
        conversation_summary=_summary_with_memories(conversation, turn),
        recent_messages=recent,
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
    user_message = HumanMessage(
        content=turn["user_input"], id=f"{turn['run_id']}-user"
    )
    return {"turn": turn, "conversation": {"messages": [user_message]}}


async def _manage_context(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    """Sliding window plus structured dynamic compression.

    Overflow messages are summarized by the model into the structured
    ConversationSummary (bounded merge keeps size controlled across rounds);
    on model failure the window still trims deterministically.
    """
    conversation = state["conversation"]
    _kept, overflow = plan_context_window(conversation["messages"])
    if not overflow:
        return {}
    removals = [RemoveMessage(id=message.id) for message in overflow if message.id]
    updates: dict[str, Any] = {}
    if removals:
        updates["messages"] = removals

    context = runtime.context
    gateway = context.model_gateway if context is not None else None
    overflow_text = "\n".join(
        f"- {message.type}: {str(message.content)[:400]}"
        for message in overflow
        if str(message.content).strip()
    )
    if gateway is not None and overflow_text:
        try:
            current = conversation["summary"]
            response = await gateway.invoke(
                role=SUMMARIZER_ROLE,
                messages=task_messages(
                    instruction="保留事实与用户约束，压缩会话记录。",
                    task=state["turn"]["user_input"], constraints=current.user_constraints,
                    prompt=(
                            "你是一次会话上下文压缩器。请把以下较早的对话内容"
                            "合并进当前会话摘要，保留用户约束、实体指代、"
                            "未解决问题与已有结论。\n"
                            '只输出 JSON：{"topic", "user_constraints": [], '
                            '"established_facts": [], "referenced_entities": {}, '
                            '"unresolved_questions": [], "previous_conclusions": []}。\n\n'
                            f"当前摘要：{current.model_dump(mode='json')}\n\n"
                            f"被压缩的对话：\n{overflow_text}"
                        )
                ),
            )
            from deeptrace.strategies.model_io import payload_text

            incoming = ConversationSummary.model_validate_json(
                payload_text(response)
            )
            updates["summary"] = merge_summaries(current, incoming)
        except Exception:
            # deterministic fallback: window trimmed, summary unchanged
            logging.getLogger(__name__).warning(
                "conversation summary compression failed; keeping prior summary",
                exc_info=True,
            )
    if not updates:
        return {}
    return {"conversation": updates}


def _finalize_answer_message(state: HarnessState) -> dict[str, Any] | None:
    response = state["turn"].get("response_outcome")
    if response is None or not str(response.content).strip():
        return None
    return {
        "conversation": {
            "messages": [
                AIMessage(
                    content=response.content,
                    id=f"{state['turn']['run_id']}-assistant",
                )
            ]
        }
    }


def _classify_intent(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    conversation = state["conversation"]
    prior_evidence = bool(conversation["evidence_ids"])
    intent = classify_intent(turn["user_input"], prior_evidence=prior_evidence)
    turn["intent"] = intent
    turn["requires_research"] = intent in {
        ConversationIntent.RESEARCH,
        ConversationIntent.INCREMENTAL_RESEARCH,
    }
    if not turn["requires_research"]:
        turn["response_mode"] = response_mode_for_intent(
            intent, turn["user_input"]
        )
        turn["active_evidence_ids"] = list(conversation["evidence_ids"])
    return {"turn": turn}


def _route_intent(state: HarnessState) -> str:
    turn = state["turn"]
    intent = turn["intent"]
    if turn["requires_research"]:
        return turn["selected_mode"].value
    if intent is ConversationIntent.SWITCH_MODE:
        return "switch_mode"
    if intent is ConversationIntent.MEMORY_UPDATE:
        return "memory_update"
    return "direct_response"


def _switch_mode_node(state: HarnessState) -> dict[str, Any]:
    turn = dict(state["turn"])
    requested: ResearchMode | None = None
    match = _MODE_PATTERN.search(turn["user_input"])
    if match:
        token = match.group(1).lower().replace("_", "").replace("-", "")
        if "plan" in token and "execute" in token:
            requested = ResearchMode.PLAN_EXECUTE
        elif "multiagent" in token or "多智能体" in (match.group(1) or ""):
            requested = ResearchMode.MULTI_AGENT
        elif "workflow" in token:
            requested = ResearchMode.WORKFLOW
    if requested is None:
        requested = turn["selected_mode"]
    turn["selected_mode"] = requested
    turn["response_outcome"] = ResponseOutcome(
        response_mode=ResponseMode.ANSWER,
        content=f"已切换到 {requested.value} 模式，下次研究将按新模式执行。",
        citations=[],
        cited_evidence_ids=[],
        partial_reason="mode_switched",
    )
    return {
        "turn": turn,
        "conversation": {"active_mode": requested},
    }


def _select_response_mode(
    state: HarnessState, config: RunnableConfig
) -> dict[str, Any]:
    turn = dict(state["turn"])
    override = (config.get("configurable") or {}).get("response_mode_override")
    if override is not None:
        if isinstance(override, ResponseMode):
            turn["response_mode"] = override
        else:
            turn["response_mode"] = ResponseMode(str(override))
    elif turn.get("requires_research", True):
        turn["response_mode"] = select_response_mode(turn["user_input"])
    # Direct-response turns keep the intent-driven response mode.
    return {"turn": turn}


def _route_response(state: HarnessState) -> str:
    turn = state["turn"]
    if not turn["requires_research"] and turn["research_outcome"] is None:
        return turn["response_mode"].value
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
        summary = state["conversation"]["summary"]
        summary_notes = (
            [f"会话主题：{summary.topic}"] if summary.topic else []
        ) + [
            f"已确认结论：{line}" for line in summary.previous_conclusions[:5]
        ]
        recent = [
            "{}：{}".format(
                "用户" if message.type == "human" else "助手",
                str(message.content)[:400],
            )
            for message in state["conversation"]["messages"][-8:]
            if str(message.content).strip()
        ]
        notes = (
            summary_notes
            + [
                f"记忆：{memory['content'][:200]}"
                for memory in (turn.get("recalled_memories") or [])
            ]
            + recent
        )[:24]
        response_input = ResponseInput(
            constraints=list(summary.user_constraints) + [m["content"] for m in turn.get("recalled_memories", []) if m.get("type") == "preference"],
            question=turn["user_input"],
            response_mode=mode,
            research_outcome=turn["research_outcome"],
            active_evidence_ids=list(turn["active_evidence_ids"]),
            context_notes=notes,
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
    if turn.get("requires_research", True):
        research_usable = (
            research is not None and research.termination_reason == "completed"
        )
    else:
        research_usable = True
    response_usable = response is not None and response.partial_reason is None
    if research_usable and response_usable:
        turn["status"] = ExecutionStatus.COMPLETED
    else:
        turn["status"] = ExecutionStatus.PARTIAL
    updates: dict[str, Any] = {"turn": turn}
    response = turn.get("response_outcome")
    if response is not None and str(response.content).strip():
        updates["conversation"] = {
            "messages": [
                AIMessage(
                    content=response.content,
                    id=f"{turn['run_id']}-assistant",
                )
            ]
        }
    return updates


def build_agent_runtime_graph(
    registry: StrategyRegistry,
    response_registry: ResponseGraphRegistry,
    checkpointer=None,
):
    builder = StateGraph(HarnessState, context_schema=HarnessContext)
    builder.add_node("initialize_turn", _initialize_turn)
    builder.add_node("manage_context", _manage_context)
    builder.add_node("classify_intent", _classify_intent)
    builder.add_node("recall_memory", _recall_memory)
    for mode in ResearchMode:
        builder.add_node(mode.value, _mode_node(registry, mode))
        builder.add_edge(mode.value, "consolidate_memory")
    builder.add_node("consolidate_memory", _consolidate_memory)
    builder.add_edge("consolidate_memory", "select_response_mode")
    builder.add_node("switch_mode", _switch_mode_node)
    builder.add_edge("switch_mode", "finalize_turn")
    builder.add_node("memory_update", _memory_update_node)
    builder.add_edge("memory_update", "finalize_turn")
    builder.add_node("select_response_mode", _select_response_mode)
    for mode in ResponseMode:
        builder.add_node(mode.value, _response_node(response_registry, mode))
        builder.add_edge(mode.value, "finalize_turn")
    builder.add_node("finalize_turn", _finalize_turn)
    builder.add_edge(START, "initialize_turn")
    builder.add_edge("initialize_turn", "manage_context")
    builder.add_edge("manage_context", "classify_intent")
    builder.add_edge("classify_intent", "recall_memory")
    builder.add_conditional_edges(
        "recall_memory",
        _route_intent,
        {
            **{mode.value: mode.value for mode in ResearchMode},
            "direct_response": "select_response_mode",
            "switch_mode": "switch_mode",
            "memory_update": "memory_update",
        },
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
