from __future__ import annotations

import inspect
import json
import re
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ResearchMode
from deeptrace.strategies.multi_agent.graph import build_multi_agent_research_graph
from deeptrace.strategies.topic import build_research_topic_graph

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


def _research_input(question: str) -> dict[str, Any]:
    return {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": question,
        "conversation_summary": {},
        "prior_evidence_ids": [],
        "unresolved_gaps": [],
        "budget": {},
        "current_date": "2026-09-13",
        "timezone": "Asia/Shanghai",
    }


def _evaluation_with_prompt_evidence(prompt: str, *, action: str = "complete") -> str:
    ids = sorted(set(re.findall(r"evidence-[0-9a-f]+", prompt)))
    findings = [
        {
            "id": "finding-1",
            "claim": "claim",
            "evidence_ids": ids[:1],
            "confidence": 0.9,
        }
    ] if ids else []
    return json.dumps(
        {
            "action": action,
            "reason": "ok",
            "findings": findings,
            "unresolved_gaps": [],
        }
    )


async def _run_multi_agent(
    model: ScriptedModelGateway,
    fixture,
    *,
    question: str = "研究 Harness 演进",
    max_researchers: int = 5,
    max_follow_ups: int = 1,
    checkpointer=None,
):
    graph = build_multi_agent_research_graph(
        build_research_topic_graph(),
        max_researchers=max_researchers,
        max_follow_ups=max_follow_ups,
        checkpointer=checkpointer,
    )
    result = await graph.ainvoke(
        _research_input(question),
        config={"configurable": {"thread_id": "ma-thread"}} if checkpointer else None,
        context=fixture.context,
    )
    return result


@pytest.mark.asyncio
async def test_supervisor_plans_and_researchers_fan_out_concurrently() -> None:
    model = ScriptedModelGateway(
        {
            "supervisor": json.dumps(
                {"assignments": ["研究方向 A", "研究方向 B"]}
            ),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究方向 A": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ],
            "研究方向 B": [
                {"url": "https://example.com/b", "title": "B", "snippet": "s"}
            ],
        },
        pages={
            "https://example.com/a": "body-a",
            "https://example.com/b": "body-b",
        },
        model_gateway=model,
    )

    result = await _run_multi_agent(model, fixture)
    outcome = result["outcome"]

    assert [role for role, _ in model.calls] == ["supervisor", "evaluator"]
    assert outcome.mode is ResearchMode.MULTI_AGENT
    assert outcome.termination_reason == "completed"
    assert len(outcome.evidence_ids) == 2
    assert result["round_number"] == 0
    assert outcome.executed_steps == 1 + 4 + 1


@pytest.mark.asyncio
async def test_researcher_failure_is_task_local_and_siblings_survive() -> None:
    model = ScriptedModelGateway(
        {
            "supervisor": json.dumps({"assignments": ["好方向", "坏方向"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "好方向": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ],
            "坏方向": [
                {"url": "https://example.com/broken", "title": "B", "snippet": "s"}
            ],
        },
        pages={"https://example.com/a": "body-a"},
        fetch_failures={"https://example.com/broken": "raise"},
        model_gateway=model,
    )

    result = await _run_multi_agent(model, fixture)
    outcome = result["outcome"]

    assert len(outcome.evidence_ids) == 1
    assert any("坏方向" in gap for gap in outcome.unresolved_gaps)
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_supervisor_never_touches_the_tool_gateway() -> None:
    model = ScriptedModelGateway(
        {
            "supervisor": json.dumps({"assignments": ["方向 A"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "方向 A": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    await _run_multi_agent(model, fixture)

    assert fixture.gateway.calls, "researchers must use the gateway"
    for call in fixture.gateway.calls:
        assert call["caller"].caller_id.startswith("researcher-")
        assert call["caller"].mode is ResearchMode.MULTI_AGENT


@pytest.mark.asyncio
async def test_researcher_branches_are_isolated_per_assignment() -> None:
    model = ScriptedModelGateway(
        {
            "supervisor": json.dumps({"assignments": ["方向 A", "方向 B"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "方向 A": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ],
            "方向 B": [
                {"url": "https://example.com/b", "title": "B", "snippet": "s"}
            ],
        },
        model_gateway=model,
    )

    await _run_multi_agent(model, fixture)

    by_caller: dict[str, list[str]] = {}
    for call in fixture.gateway.calls:
        by_caller.setdefault(call["caller"].caller_id, []).append(
            call["request"].arguments.get("query") or call["request"].arguments.get("url")
        )
    researcher_ids = sorted(by_caller)
    assert len(researcher_ids) == 2
    queries_per_researcher = {
        caller: [value for value in values if value and not value.startswith("http")]
        for caller, values in by_caller.items()
    }
    assert all(
        len(queries) == 1 for queries in queries_per_researcher.values()
    )


@pytest.mark.asyncio
async def test_follow_up_rounds_are_bounded() -> None:
    calls = {"evaluator": 0}

    def evaluator(prompt: str) -> str:
        calls["evaluator"] += 1
        return _evaluation_with_prompt_evidence(prompt, action="follow_up")

    follow_calls = {"n": 0}

    def follow_up_planner(prompt: str) -> str:
        follow_calls["n"] += 1
        return json.dumps({"assignments": [f"补充方向-{follow_calls['n']}"]})

    model = ScriptedModelGateway(
        {
            "supervisor": json.dumps({"assignments": ["初始方向"]}),
            "evaluator": evaluator,
            "follow_up": follow_up_planner,
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "初始方向": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ],
            "补充方向-1": [
                {"url": "https://example.com/b", "title": "B", "snippet": "s"}
            ],
            "补充方向-2": [
                {"url": "https://example.com/c", "title": "C", "snippet": "s"}
            ],
        },
        model_gateway=model,
    )

    result = await _run_multi_agent(model, fixture, max_follow_ups=1)
    outcome = result["outcome"]

    assert calls["evaluator"] == 2
    assert result["round_number"] == 1
    assert outcome.termination_reason == "max_follow_ups_reached"


@pytest.mark.asyncio
async def test_follow_up_assignments_skip_already_dispatched_queries() -> None:
    actions = iter(["follow_up", "complete"])
    model = ScriptedModelGateway(
        {
            "supervisor": json.dumps({"assignments": ["初始方向"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, action=next(actions)
            ),
            "follow_up": json.dumps({"assignments": ["初始方向", "新方向"]}),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "初始方向": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ],
            "新方向": [
                {"url": "https://example.com/b", "title": "B", "snippet": "s"}
            ],
        },
        model_gateway=model,
    )

    result = await _run_multi_agent(model, fixture)
    outcome = result["outcome"]

    assert "新方向" in fixture.search.calls
    assert fixture.search.calls.count("初始方向") == 1
    assert outcome.termination_reason == "completed"
    assert len(outcome.evidence_ids) == 2


@pytest.mark.asyncio
async def test_supervisor_plan_failure_falls_back_to_the_question() -> None:
    model = ScriptedModelGateway(
        {
            "supervisor": RuntimeError("supervisor down"),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究 Harness 演进": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    result = await _run_multi_agent(model, fixture)
    outcome = result["outcome"]

    assert fixture.search.calls == ["研究 Harness 演进"]
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_loop_state_is_checkpointed_without_handwritten_loops() -> None:
    model = ScriptedModelGateway(
        {
            "supervisor": json.dumps({"assignments": ["方向 A"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "方向 A": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "unique-ma-body-a"},
        model_gateway=model,
    )
    checkpointer = InMemorySaver()

    result = await _run_multi_agent(model, fixture, checkpointer=checkpointer)
    assert result["outcome"].termination_reason == "completed"

    snapshot = await build_multi_agent_research_graph(
        build_research_topic_graph(), checkpointer=checkpointer
    ).aget_state({"configurable": {"thread_id": "ma-thread"}})
    for field in ("assignments", "round_number", "researcher_outcomes"):
        assert field in snapshot.values
    serialized = json.dumps(snapshot.values, default=str, ensure_ascii=False)
    assert "unique-ma-body-a" not in serialized

    from deeptrace.strategies.multi_agent import graph as ma_graph_module

    assert "while " not in inspect.getsource(ma_graph_module)
