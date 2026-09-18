from __future__ import annotations

import json
import re
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ResearchMode
from deeptrace.strategies.plan_execute.graph import build_plan_execute_research_graph
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


async def _run_plan_execute(
    model: ScriptedModelGateway,
    fixture,
    *,
    question: str = "研究 Harness 演进",
    max_tasks: int = 6,
    max_replans: int = 2,
    checkpointer=None,
    topic_graph=None,
):
    graph = build_plan_execute_research_graph(
        topic_graph or build_research_topic_graph(),
        max_tasks=max_tasks,
        max_replans=max_replans,
        checkpointer=checkpointer,
    )
    result = await graph.ainvoke(
        _research_input(question),
        config={"configurable": {"thread_id": "pe-thread"}} if checkpointer else None,
        context=fixture.context,
    )
    return result


@pytest.mark.asyncio
async def test_plan_select_execute_evaluate_completes() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["任务一", "任务二"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "任务一": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ],
            "任务二": [
                {"url": "https://example.com/b", "title": "B", "snippet": "s"}
            ],
        },
        pages={
            "https://example.com/a": "body-a",
            "https://example.com/b": "body-b",
        },
        model_gateway=model,
    )

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    assert [role for role, _ in model.calls] == ["planner", "evaluator"]
    assert outcome.mode is ResearchMode.PLAN_EXECUTE
    assert outcome.termination_reason == "completed"
    assert len(outcome.evidence_ids) == 2
    assert result["completed_tasks"] == ["任务一", "任务二"]
    assert result["replan_count"] == 0
    assert outcome.executed_steps == 1 + 4 + 1


@pytest.mark.asyncio
async def test_planner_failure_falls_back_to_the_question() -> None:
    model = ScriptedModelGateway(
        {
            "planner": RuntimeError("planner down"),
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

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    assert result["plan_tasks"] == []
    assert result["completed_tasks"] == ["研究 Harness 演进"]
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_task_failure_becomes_gap_but_sibling_evidence_survives() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["好任务", "空任务"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "好任务": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    assert len(outcome.evidence_ids) == 1
    assert any("空任务" in gap for gap in outcome.unresolved_gaps)
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_zero_evidence_terminates_as_no_sources_without_evaluation() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": "must not run",
        }
    )
    fixture = build_gateway_fixture(
        default_search_results=[], model_gateway=model
    )

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    assert outcome.termination_reason == "no_sources"
    assert outcome.evidence_ids == []
    assert [role for role, _ in model.calls] == ["planner"]


@pytest.mark.asyncio
async def test_replanning_is_bounded_and_terminates_deterministically() -> None:
    calls = {"evaluator": 0}

    def evaluator(prompt: str) -> str:
        calls["evaluator"] += 1
        return _evaluation_with_prompt_evidence(prompt, action="replan")

    replan_calls = {"n": 0}

    def replanner(prompt: str) -> str:
        replan_calls["n"] += 1
        return json.dumps({"queries": [f"新任务-{replan_calls['n']}"]})

    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": evaluator,
            "replanner": replanner,
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "q1": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}],
            "新任务-1": [
                {"url": "https://example.com/b", "title": "B", "snippet": "s"}
            ],
            "新任务-2": [
                {"url": "https://example.com/c", "title": "C", "snippet": "s"}
            ],
        },
        model_gateway=model,
    )

    result = await _run_plan_execute(model, fixture, max_replans=2)
    outcome = result["outcome"]

    assert calls["evaluator"] == 3
    assert result["replan_count"] == 2
    assert outcome.termination_reason == "max_replans_reached"


@pytest.mark.asyncio
async def test_replan_produces_new_tasks_and_completes() -> None:
    actions = iter(["replan", "complete"])
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["首任务"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, action=next(actions)
            ),
            "replanner": json.dumps({"queries": ["首任务", "补充任务"]}),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "首任务": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ],
            "补充任务": [
                {"url": "https://example.com/b", "title": "B", "snippet": "s"}
            ],
        },
        pages={
            "https://example.com/a": "body-a",
            "https://example.com/b": "body-b",
        },
        model_gateway=model,
    )

    result = await _run_plan_execute(model, fixture, max_replans=1)
    outcome = result["outcome"]

    assert "补充任务" in fixture.search.calls
    assert "首任务" not in fixture.search.calls[1:]  # never re-executed
    assert outcome.termination_reason == "completed"
    assert len(outcome.evidence_ids) == 2


@pytest.mark.asyncio
async def test_evaluator_parse_failure_yields_deterministic_partial() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": "garbage",
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "q1": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    assert outcome.termination_reason == "insufficient_evidence"
    assert "evaluation_unavailable" in outcome.unresolved_gaps


@pytest.mark.asyncio
async def test_decision_cannot_cite_unknown_evidence() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": json.dumps(
                {
                    "action": "complete",
                    "reason": "ok",
                    "findings": [
                        {
                            "id": "finding-1",
                            "claim": "hallucinated",
                            "evidence_ids": ["evidence-bogus"],
                            "confidence": 0.9,
                        }
                    ],
                    "unresolved_gaps": [],
                }
            ),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "q1": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    assert outcome.findings == []
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_loop_state_is_checkpointed_without_handwritten_loops() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1", "q2"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "q1": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}],
            "q2": [{"url": "https://example.com/b", "title": "B", "snippet": "s"}],
        },
        pages={
            "https://example.com/a": "unique-pe-body-a",
            "https://example.com/b": "unique-pe-body-b",
        },
        model_gateway=model,
    )
    checkpointer = InMemorySaver(serde=None)

    result = await _run_plan_execute(model, fixture, checkpointer=checkpointer)
    assert result["outcome"].termination_reason == "completed"

    snapshot = await build_plan_execute_research_graph(
        build_research_topic_graph(), checkpointer=checkpointer
    ).aget_state({"configurable": {"thread_id": "pe-thread"}})
    for field in ("plan_tasks", "completed_tasks", "replan_count", "decision"):
        assert field in snapshot.values
    serialized = json.dumps(snapshot.values, default=str, ensure_ascii=False)
    assert "unique-pe-body-a" not in serialized

    import inspect

    from deeptrace.strategies.plan_execute import graph as pe_graph_module

    source = inspect.getsource(pe_graph_module)
    assert "while " not in source


class _UnfinishedPlanTopicGraph:
    """Delegates to the real topic graph but reports an open plan item."""

    def __init__(self, inner) -> None:
        self._inner = inner

    async def ainvoke(self, input_data, config=None, **kwargs):
        raw = await self._inner.ainvoke(input_data, config=config, **kwargs)
        outcome = raw["outcome"].model_copy(
            update={
                "plan_total": 3,
                "plan_completed": 2,
                "unfinished_todos": ["尚未完成的步骤"],
            }
        )
        return {"outcome": outcome}


@pytest.mark.asyncio
async def test_unfinished_executor_plan_downgrades_completed_to_incomplete() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "q1": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )
    topic = _UnfinishedPlanTopicGraph(build_research_topic_graph())

    result = await _run_plan_execute(model, fixture, topic_graph=topic)
    outcome = result["outcome"]

    assert outcome.evidence_ids
    assert outcome.termination_reason == "incomplete_plan"
