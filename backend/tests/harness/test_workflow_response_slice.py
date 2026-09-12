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
    build_multi_agent_research_graph,
    build_plan_execute_research_graph,
    build_research_topic_graph,
    build_workflow_research_graph,
)
from deeptrace.application.research import (
    ApplicationResearchRequest,
    ResearchApplicationService,
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


@pytest.mark.asyncio
async def test_plan_execute_mode_routes_through_application_service() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["研究 LangGraph Harness"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
            "responder": json.dumps({"content": "计划执行结论 [1]。"}),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究 LangGraph Harness": [
                {"url": "https://example.com/a", "title": "来源 A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "unique-pe-slice-body"},
        model_gateway=model,
    )
    strategies = StrategyRegistry()
    strategies.register(
        StrategyRegistration(
            ResearchMode.PLAN_EXECUTE,
            build_plan_execute_research_graph(build_research_topic_graph()),
        )
    )
    responses = ResponseGraphRegistry()
    responses.register(
        ResponseRegistration(ResponseMode.ANSWER, build_answer_graph())
    )
    graph = build_agent_runtime_graph(strategies, responses)

    from deeptrace.application.research import ApplicationResearchRequest

    outcome = await ResearchApplicationService(graph).invoke(
        ApplicationResearchRequest(
            run_id="run-1",
            thread_id="thread-1",
            question="研究 LangGraph Harness",
            mode=ResearchMode.PLAN_EXECUTE,
        ),
        config={"configurable": {"thread_id": "thread-1"}},
        context=fixture.context,
    )

    assert outcome.response_mode is ResponseMode.ANSWER
    assert outcome.partial_reason is None
    roles = [role for role, _ in model.calls]
    assert roles == ["planner", "evaluator", "responder"]


@pytest.mark.asyncio
async def test_multi_agent_mode_routes_through_application_service() -> None:
    model = ScriptedModelGateway(
        {
            "supervisor": json.dumps({"assignments": ["研究方向 A"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
            "responder": json.dumps({"content": "多智能体结论 [1]。"}),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究方向 A": [
                {"url": "https://example.com/a", "title": "来源 A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "unique-ma-slice-body"},
        model_gateway=model,
    )
    strategies = StrategyRegistry()
    strategies.register(
        StrategyRegistration(
            ResearchMode.MULTI_AGENT,
            build_multi_agent_research_graph(build_research_topic_graph()),
        )
    )
    responses = ResponseGraphRegistry()
    responses.register(
        ResponseRegistration(ResponseMode.ANSWER, build_answer_graph())
    )
    graph = build_agent_runtime_graph(strategies, responses)

    outcome = await ResearchApplicationService(graph).invoke(
        ApplicationResearchRequest(
            run_id="run-1",
            thread_id="thread-1",
            question="研究 LangGraph Harness",
            mode=ResearchMode.MULTI_AGENT,
        ),
        config={"configurable": {"thread_id": "thread-1"}},
        context=fixture.context,
    )

    assert outcome.partial_reason is None
    assert outcome.content == "多智能体结论 [1]。"
    assert [role for role, _ in model.calls][0] == "supervisor"


@pytest.mark.asyncio
async def test_follow_up_in_same_thread_answers_without_new_research() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["研究 LangGraph Harness"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
            "responder": json.dumps({"content": "根据已有资料：结论 [1]。"}),
        }
    )
    fixture = _fixture(model)
    strategies, responses = _registries()
    checkpointer = InMemorySaver(serde=create_harness_checkpoint_serializer())
    graph = build_agent_runtime_graph(
        strategies, responses, checkpointer=checkpointer
    )
    config = {"configurable": {"thread_id": "thread-1"}}
    service = ResearchApplicationService(graph)

    first = await service.invoke(
        ApplicationResearchRequest(
            run_id="run-1",
            thread_id="thread-1",
            question="研究 LangGraph Harness",
            mode=ResearchMode.WORKFLOW,
        ),
        config=config,
        context=fixture.context,
    )
    assert first.partial_reason is None
    tool_calls_after_first_turn = len(fixture.gateway.calls)

    second = await service.invoke(
        ApplicationResearchRequest(
            run_id="run-2",
            thread_id="thread-1",
            question="总结一下上面的要点",
            mode=ResearchMode.WORKFLOW,
        ),
        config=config,
        context=fixture.context,
    )

    assert second.response_mode is ResponseMode.BRIEF
    assert second.partial_reason is None
    assert second.cited_evidence_ids == first.cited_evidence_ids
    # no new research happened for the follow-up turn
    assert len(fixture.gateway.calls) == tool_calls_after_first_turn
    assert [role for role, _ in model.calls][-1] == "responder"


@pytest.mark.asyncio
async def test_report_request_after_research_skips_new_research() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["研究 LangGraph Harness"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
            "responder": json.dumps({"content": "# 报告\n结论 [1]。"}),
        }
    )
    fixture = _fixture(model)
    strategies, responses = _registries()
    checkpointer = InMemorySaver(serde=create_harness_checkpoint_serializer())
    graph = build_agent_runtime_graph(
        strategies, responses, checkpointer=checkpointer
    )
    config = {"configurable": {"thread_id": "thread-1"}}
    service = ResearchApplicationService(graph)
    first_request = ApplicationResearchRequest(
        run_id="run-1",
        thread_id="thread-1",
        question="研究 LangGraph Harness",
        mode=ResearchMode.WORKFLOW,
    )
    second_request = ApplicationResearchRequest(
        run_id="run-2",
        thread_id="thread-1",
        question="请生成报告",
        mode=ResearchMode.WORKFLOW,
    )

    await service.invoke(first_request, config=config, context=fixture.context)
    calls_after_research = len(fixture.gateway.calls)
    outcome = await service.invoke(
        second_request, config=config, context=fixture.context
    )

    assert outcome.response_mode is ResponseMode.REPORT
    assert outcome.partial_reason is None
    assert len(fixture.gateway.calls) == calls_after_research
    assert "正式报告" in model.calls[-1][1]


@pytest.mark.asyncio
async def test_incremental_research_runs_again_in_same_thread() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["研究 LangGraph Harness"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
            "responder": json.dumps({"content": "增量结论 [1]。"}),
        }
    )
    fixture = _fixture(model)
    strategies, responses = _registries()
    checkpointer = InMemorySaver(serde=create_harness_checkpoint_serializer())
    graph = build_agent_runtime_graph(
        strategies, responses, checkpointer=checkpointer
    )
    config = {"configurable": {"thread_id": "thread-1"}}
    service = ResearchApplicationService(graph)
    first_request = ApplicationResearchRequest(
        run_id="run-1",
        thread_id="thread-1",
        question="研究 LangGraph Harness",
        mode=ResearchMode.WORKFLOW,
    )
    second_request = ApplicationResearchRequest(
        run_id="run-2",
        thread_id="thread-1",
        question="再查一下 2026 年的最新进展",
        mode=ResearchMode.WORKFLOW,
    )

    await service.invoke(first_request, config=config, context=fixture.context)
    calls_after_first = len(fixture.gateway.calls)
    outcome = await service.invoke(
        second_request, config=config, context=fixture.context
    )

    assert outcome.partial_reason is None
    assert len(fixture.gateway.calls) > calls_after_first


@pytest.mark.asyncio
async def test_switch_mode_updates_conversation_without_research() -> None:
    model = ScriptedModelGateway({"planner": "unused", "evaluator": "unused"})
    fixture = _fixture(model)
    strategies, responses = _registries()
    graph = build_agent_runtime_graph(strategies, responses)
    service = ResearchApplicationService(graph)

    outcome = await service.invoke(
        ApplicationResearchRequest(
            run_id="run-1",
            thread_id="thread-1",
            question="切换到 plan_execute 模式",
            mode=ResearchMode.WORKFLOW,
        ),
        config={"configurable": {"thread_id": "thread-1"}},
        context=fixture.context,
    )

    assert outcome.partial_reason == "mode_switched"
    assert fixture.gateway.calls == []
    assert model.calls == []
