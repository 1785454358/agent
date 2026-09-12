from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deeptrace.domain import (
    ConversationIntent,
    ExecutionStatus,
    MemoryRecord,
    MemoryType,
    ResearchInput,
    ResearchOutcome,
    ResearchMode,
    ResponseInput,
    ResponseMode,
    ResponseOutcome,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.memory.forget import apply_lifecycle
from deeptrace.harness.memory.recall import select_memories, should_recall
from deeptrace.harness.memory.store import InMemoryMemoryStore
from deeptrace.harness.memory.write import MemoryWritePolicy, remember
from deeptrace.harness.policies.context import plan_context_window
from deeptrace.harness.policies.intent import (
    classify_intent,
    response_mode_for_intent,
)
from deeptrace.harness.registry import ResponseGraphRegistry, StrategyRegistry
from deeptrace.harness.state import HarnessState
from deeptrace.responses.citations import select_response_mode


_MODE_PATTERN = re.compile(
    r"(workflow|plan.?execute|multi.?agent|多智能体)", re.IGNORECASE
)


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
    user_message = HumanMessage(
        content=turn["user_input"], id=f"{turn['run_id']}-user"
    )
    return {"turn": turn, "conversation": {"messages": [user_message]}}


def _manage_context(state: HarnessState) -> dict[str, Any]:
    conversation = state["conversation"]
    _kept, overflow = plan_context_window(conversation["messages"])
    if not overflow:
        return {}
    removals = [
        RemoveMessage(id=message.id) for message in overflow if message.id
    ]
    if not removals:
        return {}
    return {"conversation": {"messages": removals}}


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


_MEMORY_LEAD_PATTERNS = (
    "记住我",
    "记住",
    "请记住",
    "帮我记住",
    "以后",
)


def _extract_memory_content(user_input: str) -> str:
    text = (user_input or "").strip()
    for prefix in ("请帮我记住，", "请帮我记住", "请记住，", "请记住", "帮我记住，", "帮我记住", "记住，", "记住我", "记住"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip(" ，,。:：")
            break
    if not text:
        text = user_input.strip()
    return text[:2_000]


async def _recall_memory(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    turn = dict(state["turn"])
    context = runtime.context
    memory_store = context.memory_store if context is not None else None
    if memory_store is None:
        return {"turn": turn}
    prior_evidence = bool(state["conversation"]["evidence_ids"])
    if not should_recall(turn["intent"], prior_evidence=prior_evidence):
        return {"turn": turn}
    now = runtime.context.clock.now()
    records: list[Any] = []
    records.extend(
        await memory_store.list_namespace(
            ("user", runtime.context.user_id, "preferences")
        )
    )
    records.extend(
        await memory_store.list_namespace(
            ("workspace", runtime.context.workspace_id, "facts")
        )
    )
    ranked = select_memories(
        records, query=turn["user_input"], now=now, limit=5
    )
    turn["recalled_memory_ids"] = [record.id for record in ranked]
    return {"turn": turn}


async def _memory_update_node(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    turn = dict(state["turn"])
    content = _extract_memory_content(turn["user_input"])
    context = runtime.context
    memory_store = context.memory_store if context is not None else None
    if memory_store is None:
        turn["response_outcome"] = ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="记忆功能当前不可用，未能保存。",
            citations=[],
            cited_evidence_ids=[],
            partial_reason="memory_unavailable",
        )
        return {"turn": turn}
    now = runtime.context.clock.now()
    record = MemoryRecord(
        type=MemoryType.PREFERENCE,
        namespace=("user", runtime.context.user_id, "preferences"),
        subject=content[:200],
        content=content,
        confidence=1.0,
        created_at=now,
        updated_at=now,
    )
    policy = MemoryWritePolicy()
    if not policy.can_store(record, source="user_request"):
        turn["response_outcome"] = ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="这条内容不符合保存策略，未能记住。",
            citations=[],
            cited_evidence_ids=[],
            partial_reason="memory_rejected",
        )
        return {"turn": turn}
    await remember(memory_store, record, policy)
    turn["response_outcome"] = ResponseOutcome(
        response_mode=ResponseMode.ANSWER,
        content=f"已记住：{content}",
        citations=[],
        cited_evidence_ids=[],
        partial_reason="memory_updated",
    )
    return {"turn": turn}


async def _consolidate_memory(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    context = runtime.context
    memory_store = context.memory_store if context is not None else None
    if memory_store is None:
        return {}
    turn = state["turn"]
    outcome = turn.get("research_outcome")
    if outcome is None or not outcome.findings:
        return {}
    now = runtime.context.clock.now()
    policy = MemoryWritePolicy()
    for finding in outcome.findings[:20]:
        record = MemoryRecord(
            type=MemoryType.FACT,
            namespace=("workspace", runtime.context.workspace_id, "facts"),
            subject=finding.id[:200],
            content=finding.claim,
            source_evidence_ids=list(finding.evidence_ids),
            confidence=finding.confidence,
            created_at=now,
            updated_at=now,
        )
        if policy.can_store(record, source="consolidation"):
            await remember(memory_store, record, policy)
    return {}


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
    return {"turn": turn}


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
