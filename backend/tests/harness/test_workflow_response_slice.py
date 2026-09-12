"""Integration tests for the Workflow → Response vertical slice."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ExecutionStatus, ResearchMode, ResponseMode
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.harness.state import new_conversation, new_turn
from deeptrace.responses import (
    build_answer_graph,
    build_brief_graph,
    build_report_graph,
)
from deeptrace.strategies import (
    build_research_topic_graph,
    build_workflow_research_graph,
)

from strategies.fixtures import build_gateway_fixture


class ScriptedModelGateway:
    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    async def invoke(self, *, role: str, messages: list[Any]) -> Any:
        prompt = str(messages[-1].content)
        self.calls.append((role, prompt))
        response = self._responses[role]
        if callable(response):
            response = response(prompt)
        if isinstance(response, Exception):
            raise response
        return response


def _evaluation_with_prompt_evidence(prompt: str, *, sufficient: bool) -> str:
    ids = sorted(set(re.findall(r"evidence-[0-9a-f]+", prompt)))
    findings = [
        {
            "id": "finding-1",
            "claim": "已获得可用资料",
            "evidence_ids": ids[:1],
            "confidence": 0.9,
        }
    ]
    return json.dumps(
        {"findings": findings, "unresolved_gaps": [], "sufficient": sufficient}
    )


def _registries() -> tuple[StrategyRegistry, ResponseGraphRegistry]:
    strategies = StrategyRegistry()
    strategies.register(
        StrategyRegistration(
            ResearchMode.WORKFLOW,
            build_workflow_research_graph(build_research_topic_graph()),
        )
    )
    responses = ResponseGraphRegistry()
    responses.register(ResponseRegistration(ResponseMode.ANSWER, build_answer_graph()))
    responses.register(ResponseRegistration(ResponseMode.BRIEF, build_brief_graph()))
    responses.register(
        ResponseRegistration(ResponseMode.REPORT, build_report_graph())
    )
    return strategies, responses


def _initial_state(user_input: str):
    return {
        "conversation": new_conversation("thread-1", ResearchMode.WORKFLOW),
        "turn": new_turn("run-1", user_input, ResearchMode.WORKFLOW),
    }


def _fixture(model: ScriptedModelGateway):
    return build_gateway_fixture(
        search_results={
            "研究 LangGraph Harness": [
                {"url": "https://example.com/a", "title": "来源 A", "snippet": "s"}
            ],
            "研究 LangGraph Harness II": [
                {"url": "https://example.com/b", "title": "来源 B", "snippet": "s"}
            ],
        },
        pages={
            "https://example.com/a": "unique-evidence-body-a",
            "https://example.com/b": "unique-evidence-body-b",
        },
        model_gateway=model,
    )


@pytest.mark.asyncio
async def test_default_request_returns_a_concise_cited_answer() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["研究 LangGraph Harness"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
            "responder": json.dumps({"content": "研究结论如下 [1]。"}),
        }
    )
    fixture = _fixture(model)
    strategies, responses = _registries()
    checkpointer = InMemorySaver(serde=create_harness_checkpoint_serializer())
    graph = build_agent_runtime_graph(
        strategies, responses, checkpointer=checkpointer
    )

    result = await graph.ainvoke(
        _initial_state("研究 LangGraph Harness"),
        config={"configurable": {"thread_id": "thread-1"}},
        context=fixture.context,
    )

    turn = result["turn"]
    assert turn["status"] is ExecutionStatus.COMPLETED
    assert turn["response_mode"] is ResponseMode.ANSWER
    assert turn["response_outcome"].partial_reason is None
    assert turn["response_outcome"].citations[0].evidence_id == (
        turn["research_outcome"].evidence_ids[0]
    )
    # real typed tool calls happened through the gateway
    tool_sequence = [call["request"].tool.value for call in fixture.gateway.calls]
    assert tool_sequence == ["search_web", "fetch_page"]
    assert turn["research_outcome"].executed_steps >= 3

    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": "thread-1"}}
    )
    serialized = json.dumps(snapshot.values, default=str, ensure_ascii=False)
    assert "unique-evidence-body-a" not in serialized
    for private_key in ("search_result", "loaded_evidence", "topic_input"):
        assert private_key not in snapshot.values

    checkpoints = [
        item
        async for item in checkpointer.alist(
            {"configurable": {"thread_id": "thread-1"}}
        )
    ]
    namespaces = {
        item.config["configurable"].get("checkpoint_ns") for item in checkpoints
    }
    assert any(ns and ns.startswith("workflow") for ns in namespaces)
    assert any("research_topic" in ns for ns in namespaces)
    assert any(ns and ns.startswith("answer") for ns in namespaces)


@pytest.mark.asyncio
async def test_explicit_report_request_reuses_research_and_routes_to_report() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["研究 LangGraph Harness"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
            "responder": json.dumps({"content": "# 正式报告\n结论 [1]。"}),
        }
    )
    fixture = _fixture(model)
    strategies, responses = _registries()
    graph = build_agent_runtime_graph(strategies, responses)

    result = await graph.ainvoke(
        _initial_state("请生成报告"),
        config={"configurable": {"thread_id": "thread-1"}},
        context=fixture.context,
    )

    turn = result["turn"]
    assert turn["response_mode"] is ResponseMode.REPORT
    assert turn["response_outcome"].response_mode is ResponseMode.REPORT
    assert "正式报告" in model.calls[-1][1]
    # the same research strategy and evidence still backed the report
    assert turn["response_outcome"].citations[0].evidence_id == (
        turn["research_outcome"].evidence_ids[0]
    )
