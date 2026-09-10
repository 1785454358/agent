from dataclasses import FrozenInstanceError

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from deeptrace.domain import (
    BudgetSnapshot,
    ErrorCategory,
    ErrorRecord,
    ExecutionStatus,
    Evidence,
    EvidenceLifecycleStatus,
    Finding,
    ResearchInput,
    ResearchOutcome,
    ResearchProfile,
    ResponseProfile,
    ToolName,
    ToolRequest,
    ToolResult,
)
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.state import (
    HarnessState,
    merge_conversation,
    new_conversation,
    new_turn,
)


class _UnregisteredCheckpointModel(BaseModel):
    value: str


def test_conversation_reducer_appends_messages_and_replaces_other_fields() -> None:
    initial = new_conversation("thread-1", ResearchProfile.WORKFLOW)
    merged = merge_conversation(
        initial,
        {
            "messages": [HumanMessage(content="继续")],
            "unresolved_gaps": ["国内情况"],
        },
    )
    assert [message.content for message in merged["messages"]] == ["继续"]
    assert merged["active_profile"] is ResearchProfile.WORKFLOW
    assert merged["unresolved_gaps"] == ["国内情况"]


def test_conversation_reducer_uses_message_ids_to_replace_updates() -> None:
    initial = new_conversation("thread-1", ResearchProfile.WORKFLOW)
    initial["messages"] = [HumanMessage(content="old", id="message-1")]

    merged = merge_conversation(
        initial,
        {"messages": [HumanMessage(content="new", id="message-1")]},
    )

    assert [message.content for message in merged["messages"]] == ["new"]


def test_conversation_reducer_accepts_the_first_state_graph_write() -> None:
    builder = StateGraph(HarnessState)
    builder.add_node("noop", lambda state: {})
    builder.add_edge(START, "noop")
    builder.add_edge("noop", END)
    graph = builder.compile()
    initial = {
        "conversation": new_conversation("thread-1", ResearchProfile.WORKFLOW),
        "turn": new_turn("run-1", "研究 Harness", ResearchProfile.WORKFLOW),
    }

    result = graph.invoke(initial)

    assert result["conversation"]["thread_id"] == "thread-1"


def test_conversation_reducer_rejects_unknown_update_fields() -> None:
    initial = new_conversation("thread-1", ResearchProfile.WORKFLOW)

    with pytest.raises(ValueError, match="unknown conversation fields"):
        merge_conversation(initial, {"unexpected": "value"})


def test_new_turn_does_not_carry_previous_ephemeral_values() -> None:
    turn = new_turn("run-2", "继续研究", ResearchProfile.PLAN_EXECUTE)
    assert turn["status"] is ExecutionStatus.PENDING
    assert turn["response_profile"] is ResponseProfile.ANSWER
    assert turn["research_outcome"] is None
    assert turn["recalled_memory_ids"] == []


def test_new_state_is_checkpoint_serializable() -> None:
    state = {
        "conversation": new_conversation("thread-1", ResearchProfile.MULTI_AGENT),
        "turn": new_turn("run-1", "研究 Harness", ResearchProfile.MULTI_AGENT),
    }
    state["conversation"]["messages"] = [HumanMessage(content="继续")]
    finding = Finding(
        id="finding-1",
        claim="Harness state is checkpointable",
        evidence_ids=["evidence-1"],
        confidence=0.9,
    )
    state["conversation"]["established_findings"] = [finding]
    state["turn"]["research_request"] = ResearchInput(
        question="研究 Harness",
        conversation_summary=state["conversation"]["summary"],
        prior_evidence_ids=["evidence-1"],
        unresolved_gaps=["strict mode"],
        budget=BudgetSnapshot(max_model_calls=2, used_model_calls=1),
        current_date="2026-09-10",
        timezone="Asia/Shanghai",
    )
    state["turn"]["research_outcome"] = ResearchOutcome(
        profile=ResearchProfile.MULTI_AGENT,
        evidence_ids=["evidence-1"],
        findings=[finding],
        unresolved_gaps=[],
        executed_steps=1,
        termination_reason="completed",
    )
    state["turn"]["error"] = ErrorRecord(
        code="temporary_failure",
        category=ErrorCategory.AGENT_RECOVERABLE,
        retryable=True,
        source="researcher",
        node="research",
        public_message="Research can continue",
    )

    serializer = create_harness_checkpoint_serializer()
    serialized = serializer.dumps_typed(state)
    restored = serializer.loads_typed(serialized)

    assert restored == state


def test_checkpoint_serializer_does_not_reconstruct_unregistered_models() -> None:
    serializer = create_harness_checkpoint_serializer()
    value = {"custom": _UnregisteredCheckpointModel(value="blocked")}

    restored = serializer.loads_typed(serializer.dumps_typed(value))

    assert not isinstance(restored["custom"], _UnregisteredCheckpointModel)
    assert restored["custom"] == {"value": "blocked"}


def test_checkpoint_serializer_round_trips_tool_and_evidence_contracts() -> None:
    request = ToolRequest(
        request_id="request-1",
        run_id="run-1",
        thread_id="thread-1",
        call_id="call-1",
        tool=ToolName.FETCH_PAGE,
        arguments={"url": "https://example.com/research"},
    )
    result = ToolResult(
        request_id="request-1",
        run_id="run-1",
        thread_id="thread-1",
        call_id="call-1",
        tool=ToolName.FETCH_PAGE,
        ok=True,
        preview="Research summary",
        data_ref="evidence://evidence-1/body",
        evidence_ids=["evidence-1"],
    )
    evidence = Evidence(
        id="evidence-1",
        canonical_url="https://example.com/research",
        title="Research source",
        media_type="text/html",
        content_hash="sha256:" + "a" * 64,
        fetched_at="2026-09-10T08:00:00Z",
        source_quality=0.9,
        status=EvidenceLifecycleStatus.ACTIVE,
        version=1,
        metadata={"language": "en"},
    )
    value = {"request": request, "result": result, "evidence": evidence}

    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(value))

    assert restored == value
    assert isinstance(restored["request"], ToolRequest)
    assert isinstance(restored["result"], ToolResult)
    assert isinstance(restored["evidence"], Evidence)


def test_harness_context_is_immutable() -> None:
    context = HarnessContext(
        user_id="user-1",
        workspace_id="workspace-1",
        model_gateway=object(),
        tool_gateway=object(),
        evidence_store=object(),
        event_sink=object(),
        clock=object(),
    )
    with pytest.raises(FrozenInstanceError):
        context.user_id = "user-2"
