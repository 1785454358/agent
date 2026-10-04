from __future__ import annotations

import json
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AIMessage

from deeptrace.config.settings import Settings
from deeptrace.domain import ResearchMode
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.strategies.plan_execute.graph import build_plan_execute_research_graph
from strategies.fixtures import (
    ScriptedModelGateway,
    build_gateway_fixture,
    evaluation_payload_from_view,
)


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
    return json.dumps(evaluation_payload_from_view(prompt, action=action))


@pytest.mark.asyncio
async def test_nested_executor_can_use_the_increased_iteration_allowance() -> None:
    settings = Settings("test", "https://example.com", "test", "test")
    responses = []
    results = {}
    for index in range(4):
        url = f"https://example.com/{index}"
        query = f"topic-{index}"
        results[query] = [{"url": url, "title": "source", "snippet": "s"}]
        for name, arguments in [("search_web", {"query": query}), ("fetch_page", {"url": url})]:
            responses.append(AIMessage(content="", tool_calls=[{
                "name": name, "args": arguments, "id": f"{name}-{index}",
            }]))
    responses.append(AIMessage(content="done"))
    model = ScriptedModelGateway({
        "planner": json.dumps({"requirements": [{"id": "r1", "description": "核验来源"}],
                               "queries": ["initial"], "query_targets": {"initial": ["r1"]}}),
        "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
    })
    invoke_role = model.invoke

    async def invoke(**kwargs):
        if kwargs["role"] == "researcher":
            return responses.pop(0)
        return await invoke_role(**kwargs)

    model.invoke = invoke
    fixture = build_gateway_fixture(model_gateway=model, search_results=results)
    result = await _run_plan_execute(model, fixture, topic_graph=build_research_agent_graph(
        max_iterations=settings.agent_max_iterations,
    ))
    assert result["outcome"].termination_reason == "completed"
    assert result["topic_outcomes"][0].agent_outcome.iterations == 9
    assert len(result["outcome"].evidence_ids) == 4


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
        topic_graph or build_research_agent_graph(),
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
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["任务一", "任务二"],
                    "query_targets": {"任务一": ["r1"], "任务二": ["r1"]},
                }
            ),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "任务一": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}],
            "任务二": [{"url": "https://example.com/b", "title": "B", "snippet": "s"}],
        },
        pages={
            "https://example.com/a": "body-a",
            "https://example.com/b": "body-b",
        },
        model_gateway=model,
    )

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    roles = [role for role, _ in model.calls]
    assert roles.count("researcher") == 6
    assert [role for role in roles if role != "researcher"] == ["planner", "evaluator"]
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
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["好任务", "空任务"],
                    "query_targets": {"好任务": ["r1"], "空任务": ["r1"]},
                }
            ),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "好任务": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    assert len(outcome.evidence_ids) == 1
    empty_branch = next(
        branch for branch in result["topic_outcomes"] if branch.query == "空任务"
    )
    assert empty_branch.agent_outcome.stop_reason == "incomplete_plan"
    assert "agent_exit:incomplete_plan" in result["diagnostic_gaps"]
    assert outcome.unresolved_gaps == []
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_zero_evidence_terminates_as_no_sources_without_evaluation() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["q1"],
                    "query_targets": {"q1": ["r1"]},
                }
            ),
            "evaluator": "must not run",
            "replanner": json.dumps({"tasks": []}),
        }
    )
    fixture = build_gateway_fixture(default_search_results=[], model_gateway=model)

    result = await _run_plan_execute(model, fixture)
    outcome = result["outcome"]

    assert outcome.termination_reason == "no_sources"
    assert outcome.evidence_ids == []
    assert [role for role, _ in model.calls] == [
        "planner",
        *("researcher" for _ in range(4)),
        "replanner",
    ]


@pytest.mark.asyncio
async def test_replanning_is_bounded_and_terminates_deterministically() -> None:
    calls = {"evaluator": 0}

    def evaluator(prompt: str) -> str:
        calls["evaluator"] += 1
        return _evaluation_with_prompt_evidence(prompt, action="replan")

    replan_calls = {"n": 0}

    def replanner(prompt: str) -> str:
        replan_calls["n"] += 1
        return json.dumps(
            {
                "tasks": [
                    {
                        "query": f"新任务-{replan_calls['n']}",
                        "target_requirement_ids": ["r1"],
                    }
                ]
            }
        )

    model = ScriptedModelGateway(
        {
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["q1"],
                    "query_targets": {"q1": ["r1"]},
                }
            ),
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
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["首任务"],
                    "query_targets": {"首任务": ["r1"]},
                }
            ),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, action=next(actions)
            ),
            "replanner": json.dumps(
                {
                    "tasks": [
                        {"query": q, "target_requirement_ids": ["r1"]}
                        for q in ["首任务", "补充任务"]
                    ]
                }
            ),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "首任务": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}],
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
    progress = [(kind, data) for kind, data in fixture.events.events
                if kind.startswith(("planning.", "task.", "evaluation.", "replanning.", "research.route"))]
    assert [kind for kind, _ in progress] == [
        "planning.started", "planning.completed", "task.started", "task.completed",
        "evaluation.started", "evaluation.completed", "research.route",
        "replanning.started", "replanning.completed", "task.started", "task.completed",
        "evaluation.started", "evaluation.completed", "research.route",
    ]
    assert json.loads(progress[1][1]["tasks_json"]) == ["首任务"]
    assert progress[6][1]["next_step"] == "replan"
    assert progress[7][1]["round"] == 2
    assert json.loads(progress[8][1]["tasks_json"]) == ["补充任务"]
    assert progress[-1][1]["next_step"] == "finalize"
    completed_ids = {data["call_id"] for kind, data in fixture.events.events if kind == "tool.completed"}
    for kind, data in fixture.events.events:
        if kind == "agent.tool_observation" and data["tool"] in {"search_web", "fetch_page"}:
            assert data["call_id"] in completed_ids


@pytest.mark.asyncio
async def test_evaluation_logs_real_stop_instead_of_a_proposed_replan(monkeypatch):
    from langgraph.runtime import Runtime
    from deeptrace.strategies.plan_execute import nodes

    async def evaluate(*args, **kwargs):
        return {"assessment": type("Decision", (), {"action": "replan", "reason": "需要更多原文"})(),
                "unresolved_gaps": ["基础理论缺证据"], "executed_steps": 1}

    monkeypatch.setattr(nodes, "run_evidence_evaluation", evaluate)
    monkeypatch.setattr(nodes, "strong_exit_reason", lambda state: "iteration_limit")
    fixture = build_gateway_fixture()
    await nodes.build_evaluate_node(2)({"replan_count": 0}, Runtime(context=fixture.context))
    route = fixture.events.events[-1]
    assert route[0] == "research.route"
    assert route[1]["action"] == "replan"
    assert route[1]["next_step"] == "finalize"
    assert route[1]["reason"] == "iteration_limit"


@pytest.mark.asyncio
async def test_evaluator_parse_failure_yields_deterministic_partial() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["q1"],
                    "query_targets": {"q1": ["r1"]},
                }
            ),
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
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["q1"],
                    "query_targets": {"q1": ["r1"]},
                }
            ),
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
                            "supports": [
                                {
                                    "evidence_id": "evidence-bogus",
                                    "passage_id": "not-visible",
                                    "quote": "hallucinated",
                                }
                            ],
                        }
                    ],
                    "unresolved_gaps": [],
                    "coverage": {
                        "items": [
                            {
                                "requirement_id": "r1",
                                "status": "covered",
                                "reason": "claimed",
                                "finding_ids": ["finding-1"],
                            }
                        ]
                    },
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
    assert outcome.termination_reason != "completed"
    assert outcome.coverage.items[0].status == "missing"


@pytest.mark.asyncio
async def test_loop_state_is_checkpointed_without_handwritten_loops() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["q1", "q2"],
                    "query_targets": {"q1": ["r1"], "q2": ["r1"]},
                }
            ),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(prompt),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "q1": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}],
            "q2": [{"url": "https://example.com/b", "title": "B", "snippet": "s"}],
        },
        pages={
            "https://example.com/a": "unique-pe-body-a" + " background" * 700,
            "https://example.com/b": "unique-pe-body-b",
        },
        model_gateway=model,
    )
    checkpointer = InMemorySaver(serde=None)

    result = await _run_plan_execute(model, fixture, checkpointer=checkpointer)
    assert result["outcome"].termination_reason == "completed"

    snapshot = await build_plan_execute_research_graph(
        build_research_agent_graph(), checkpointer=checkpointer
    ).aget_state({"configurable": {"thread_id": "pe-thread"}})
    for field in ("plan_tasks", "completed_tasks", "replan_count", "decision"):
        assert field in snapshot.values
    serialized = json.dumps(snapshot.values, default=str, ensure_ascii=False)
    assert "unique-pe-body-a" + " background" * 700 not in serialized
    assert all(
        len(s.quote) <= 500 for f in result["outcome"].findings for s in f.supports
    )

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
            "planner": json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                    ],
                    "queries": ["q1"],
                    "query_targets": {"q1": ["r1"]},
                }
            ),
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
    topic = _UnfinishedPlanTopicGraph(build_research_agent_graph())

    result = await _run_plan_execute(model, fixture, topic_graph=topic)
    outcome = result["outcome"]

    assert outcome.evidence_ids
    assert outcome.termination_reason == "incomplete_plan"
