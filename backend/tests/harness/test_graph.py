from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deeptrace.domain import ExecutionStatus, ResearchProfile
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.graph import build_harness_graph
from deeptrace.harness.registry import ProfileRegistration, ProfileRegistry
from deeptrace.harness.state import new_conversation, new_turn


class _ChildState(TypedDict, total=False):
    question: str
    conversation_summary: dict[str, Any]
    prior_evidence_ids: list[str]
    unresolved_gaps: list[str]
    budget: dict[str, int]
    current_date: str
    timezone: str
    profile: str
    evidence_ids: list[str]
    findings: list[dict[str, Any]]
    executed_steps: int
    termination_reason: str
    _private_child_trace: str
    _private_child_user_id: str
    _private_child_thread_id: str
    _private_child_custom: str


class _ModelGateway:
    async def invoke(self, *, role: str, messages: list[Any]) -> Any:
        raise AssertionError("model gateway is not used by the harness skeleton")


class _ToolGateway:
    async def execute(self, request: Any) -> Any:
        raise AssertionError("tool gateway is not used by the harness skeleton")


class _EvidenceStore:
    async def get_many(self, evidence_ids: list[str]) -> list[Any]:
        return []


class _EventSink:
    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        return None


class _FixedClock:
    def now(self) -> datetime:
        return datetime(
            2026,
            9,
            10,
            9,
            30,
            tzinfo=timezone(timedelta(hours=8), name="Asia/Shanghai"),
        )


def _context() -> HarnessContext:
    return HarnessContext(
        user_id="user-1",
        workspace_id="workspace-1",
        model_gateway=_ModelGateway(),
        tool_gateway=_ToolGateway(),
        evidence_store=_EvidenceStore(),
        event_sink=_EventSink(),
        clock=_FixedClock(),
    )


def _profile_graph(
    profile: ResearchProfile,
    *,
    outcome_profile: ResearchProfile | None = None,
):
    def research(
        state: _ChildState,
        runtime: Runtime[HarnessContext],
        config: RunnableConfig,
    ) -> _ChildState:
        configurable = config["configurable"]
        return {
            "profile": (outcome_profile or profile).value,
            "evidence_ids": [f"ev-{profile.value}"],
            "findings": [
                {
                    "id": f"finding-{profile.value}",
                    "claim": f"{state['current_date']}|{state['timezone']}",
                    "evidence_ids": [f"ev-{profile.value}"],
                    "confidence": 1.0,
                }
            ],
            "unresolved_gaps": [],
            "executed_steps": 1,
            "termination_reason": "completed",
            "_private_child_trace": f"trace-{profile.value}",
            "_private_child_user_id": runtime.context.user_id,
            "_private_child_thread_id": configurable["thread_id"],
            "_private_child_custom": configurable["custom_marker"],
        }

    builder = StateGraph(_ChildState, context_schema=HarnessContext)
    builder.add_node("research", research)
    builder.add_edge(START, "research")
    builder.add_edge("research", END)
    return builder.compile(checkpointer=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", list(ResearchProfile))
async def test_harness_routes_to_each_registered_profile(
    profile: ResearchProfile,
) -> None:
    registry = ProfileRegistry()
    for item in ResearchProfile:
        registry.register(ProfileRegistration(item, _profile_graph(item)))
    checkpointer = InMemorySaver(serde=create_harness_checkpoint_serializer())
    graph = build_harness_graph(registry, checkpointer=checkpointer)
    thread_id = f"thread-{profile.value}"
    initial = {
        "conversation": new_conversation(thread_id, profile),
        "turn": new_turn("run-1", "研究 Harness", profile),
    }

    result = await graph.ainvoke(
        initial,
        config={
            "configurable": {
                "thread_id": thread_id,
                "custom_marker": f"custom-{profile.value}",
            }
        },
        context=_context(),
    )

    assert result["turn"]["status"] is ExecutionStatus.COMPLETED
    assert result["turn"]["research_request"].question == "研究 Harness"
    assert result["turn"]["research_request"].current_date == "2026-09-10"
    assert result["turn"]["research_request"].timezone == "Asia/Shanghai"
    assert result["turn"]["research_outcome"].profile is profile
    assert result["conversation"]["evidence_ids"] == [f"ev-{profile.value}"]
    assert result["conversation"]["established_findings"][0].claim == (
        "2026-09-10|Asia/Shanghai"
    )
    assert "_private_child_trace" not in result
    assert "_private_child_user_id" not in result
    assert "_private_child_thread_id" not in result
    assert "_private_child_custom" not in result

    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": thread_id}}
    )
    assert snapshot.values["turn"]["run_id"] == "run-1"
    assert snapshot.values["turn"]["research_outcome"].profile is profile
    assert snapshot.values["conversation"]["established_findings"][0].id == (
        f"finding-{profile.value}"
    )
    assert "_private_child_trace" not in snapshot.values
    assert "_private_child_user_id" not in snapshot.values
    assert "_private_child_thread_id" not in snapshot.values
    assert "_private_child_custom" not in snapshot.values

    checkpoints = [
        item
        async for item in checkpointer.alist(
            {"configurable": {"thread_id": thread_id}}
        )
    ]
    child_checkpoints = [
        item
        for item in checkpoints
        if item.config["configurable"].get("checkpoint_ns") == profile.value
    ]
    assert child_checkpoints
    assert any(
        item.checkpoint["channel_values"].get("_private_child_trace")
        == f"trace-{profile.value}"
        for item in child_checkpoints
    )
    assert any(
        item.checkpoint["channel_values"].get("_private_child_user_id")
        == "user-1"
        and item.checkpoint["channel_values"].get("_private_child_thread_id")
        == thread_id
        and item.checkpoint["channel_values"].get("_private_child_custom")
        == f"custom-{profile.value}"
        for item in child_checkpoints
    )


@pytest.mark.asyncio
async def test_harness_rejects_an_unregistered_selected_profile() -> None:
    registry = ProfileRegistry()
    registry.register(
        ProfileRegistration(
            ResearchProfile.WORKFLOW,
            _profile_graph(ResearchProfile.WORKFLOW),
        )
    )
    graph = build_harness_graph(registry)
    initial = {
        "conversation": new_conversation(
            "thread-1", ResearchProfile.MULTI_AGENT
        ),
        "turn": new_turn(
            "run-1", "研究 Harness", ResearchProfile.MULTI_AGENT
        ),
    }

    with pytest.raises(KeyError, match="profile is not registered"):
        await graph.ainvoke(initial)


@pytest.mark.asyncio
async def test_harness_rejects_an_outcome_for_a_different_profile() -> None:
    registry = ProfileRegistry()
    registry.register(
        ProfileRegistration(
            ResearchProfile.WORKFLOW,
            _profile_graph(
                ResearchProfile.WORKFLOW,
                outcome_profile=ResearchProfile.PLAN_EXECUTE,
            ),
        )
    )
    graph = build_harness_graph(registry)
    initial = {
        "conversation": new_conversation(
            "thread-1", ResearchProfile.WORKFLOW
        ),
        "turn": new_turn("run-1", "研究 Harness", ResearchProfile.WORKFLOW),
    }

    with pytest.raises(ValueError, match="outcome profile does not match"):
        await graph.ainvoke(
            initial,
            config={
                "configurable": {
                    "thread_id": "thread-1",
                    "custom_marker": "custom-workflow",
                }
            },
            context=_context(),
        )
