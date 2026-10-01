from __future__ import annotations

import json
import re
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ResearchInput, ResearchMode
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.strategies.workflow.graph import build_workflow_research_graph
from strategies.fixtures import ScriptedModelGateway, build_gateway_fixture


def _research_input(question: str = "研究 LangGraph Harness") -> dict[str, Any]:
    return ResearchInput(
        run_id="run-1",
        thread_id="thread-1",
        question=question,
        current_date="2026-09-12",
        timezone="Asia/Shanghai",
    ).model_dump(mode="json")


def _evidence_ids_from_prompt(prompt: str) -> list[str]:
    return sorted(set(re.findall(r"evidence-[0-9a-f]+", prompt)))


def _evaluation_with_prompt_evidence(prompt: str, *, sufficient: bool) -> str:
    ids = _evidence_ids_from_prompt(prompt)
    findings = [
        {
            "id": f"finding-{index}",
            "claim": f"claim {index}",
            "evidence_ids": [ids[index]],
            "confidence": 0.9,
        }
        for index in range(min(1, len(ids)))
    ]
    return json.dumps(
        {"findings": findings, "unresolved_gaps": [], "sufficient": sufficient}
    )


async def _run_workflow(
    model: ScriptedModelGateway,
    fixture,
    *,
    question: str = "研究 LangGraph Harness",
    query_limit: int = 3,
    checkpointer=None,
    topic_graph=None,
):
    topic_graph = topic_graph or build_research_agent_graph()
    graph = build_workflow_research_graph(
        topic_graph, query_limit=query_limit, checkpointer=checkpointer
    )
    config = (
        {"configurable": {"thread_id": "workflow-thread"}} if checkpointer else None
    )
    result = await graph.ainvoke(
        _research_input(question), config=config, context=fixture.context
    )
    return result


@pytest.mark.asyncio
async def test_workflow_routes_plan_topics_evaluate_finalize() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["query one", "query two"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "query one": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ],
            "query two": [
                {"url": "https://example.com/b", "title": "B", "snippet": "s"}
            ],
        },
        pages={
            "https://example.com/a": "body-a",
            "https://example.com/b": "body-b",
        },
        model_gateway=model,
    )

    result = await _run_workflow(model, fixture)
    outcome = result["outcome"]

    roles = [role for role, _prompt in model.calls]
    assert roles.count("researcher") == 6
    assert [role for role in roles if role != "researcher"] == ["planner", "evaluator"]
    assert result["queries"] == ["query one", "query two"]
    assert outcome.mode is ResearchMode.WORKFLOW
    assert outcome.termination_reason == "completed"
    assert len(outcome.evidence_ids) == 2
    assert len(outcome.findings) == 1
    assert set(outcome.findings[0].evidence_ids) <= set(outcome.evidence_ids)
    assert outcome.unresolved_gaps == []
    assert outcome.executed_steps == 6


@pytest.mark.asyncio
async def test_workflow_uses_queries_from_a_real_chat_message() -> None:
    model = ScriptedModelGateway(
        {"planner": AIMessage(content='{"queries":["official docs"]}')}
    )
    fixture = build_gateway_fixture(model_gateway=model)
    result = await _run_workflow(model, fixture)
    assert result["queries"] == ["official docs"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "planner_response", [RuntimeError("planner down"), "not json at all"]
)
async def test_planner_failure_falls_back_to_the_user_question(
    planner_response: Any,
) -> None:
    model = ScriptedModelGateway(
        {
            "planner": planner_response,
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究 LangGraph Harness": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    result = await _run_workflow(model, fixture)
    outcome = result["outcome"]

    assert result["queries"] == ["研究 LangGraph Harness"]
    assert len(outcome.evidence_ids) == 1
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_planner_queries_are_deduplicated_and_bounded() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1", "q1", "q2", "q3", "q4", "q5"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
        }
    )
    fixture = build_gateway_fixture(model_gateway=model)

    result = await _run_workflow(model, fixture, query_limit=3)

    assert result["queries"] == ["q1", "q2", "q3"]
    assert fixture.search.calls == ["q1", "q2", "q3"]


@pytest.mark.asyncio
async def test_one_topic_failure_is_a_gap_while_sibling_evidence_survives() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["good query", "doomed query"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "good query": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    result = await _run_workflow(model, fixture)
    outcome = result["outcome"]

    assert len(outcome.evidence_ids) == 1
    empty_branch = next(
        branch for branch in result["topic_outcomes"] if branch.query == "doomed query"
    )
    assert empty_branch.evidence_ids == []
    assert empty_branch.agent_outcome.stop_reason == "incomplete_plan"
    assert "agent_exit:incomplete_plan" in outcome.unresolved_gaps
    assert outcome.termination_reason == "incomplete_plan"


@pytest.mark.asyncio
async def test_zero_usable_evidence_yields_partial_no_sources() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": "evaluator must not run",
        }
    )
    fixture = build_gateway_fixture(default_search_results=[], model_gateway=model)

    result = await _run_workflow(model, fixture)
    outcome = result["outcome"]

    assert outcome.evidence_ids == []
    assert outcome.findings == []
    assert outcome.termination_reason == "no_sources"
    assert [role for role, _prompt in model.calls] == [
        "planner",
        *("researcher" for _ in range(4)),
    ]


@pytest.mark.asyncio
async def test_evaluation_cannot_cite_unknown_evidence() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": json.dumps(
                {
                    "findings": [
                        {
                            "id": "finding-1",
                            "claim": "hallucinated",
                            "evidence_ids": ["evidence-not-real"],
                            "confidence": 0.9,
                        }
                    ],
                    "unresolved_gaps": [],
                    "sufficient": True,
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

    result = await _run_workflow(model, fixture)
    outcome = result["outcome"]

    assert outcome.findings == []
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_evaluation_parse_failure_yields_deterministic_partial() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": "garbage from the model",
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "q1": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )

    result = await _run_workflow(model, fixture)
    outcome = result["outcome"]

    assert outcome.findings == []
    assert "evaluation_unavailable" in outcome.unresolved_gaps
    assert outcome.termination_reason == "insufficient_evidence"


@pytest.mark.asyncio
async def test_topic_execution_failure_is_a_gap_and_siblings_survive() -> None:
    class FlakyTopicGraph:
        def __init__(self, inner, fail_query: str) -> None:
            self._inner = inner
            self._fail_query = fail_query

        async def ainvoke(self, input_data, config=None, **kwargs):
            if input_data["topic_input"].query == self._fail_query:
                raise RuntimeError("topic subgraph exploded")
            return await self._inner.ainvoke(input_data, config=config, **kwargs)

    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["good", "broken"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "good": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )
    flaky = FlakyTopicGraph(build_research_agent_graph(), fail_query="broken")

    result = await _run_workflow(model, fixture, topic_graph=flaky)
    outcome = result["outcome"]

    assert len(outcome.evidence_ids) == 1
    assert any(
        "topic_execution_failed" in gap and "broken" in gap
        for gap in outcome.unresolved_gaps
    )


@pytest.mark.asyncio
async def test_workflow_state_keeps_references_and_topic_privacy() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
            ),
        }
    )
    fixture = build_gateway_fixture(
        search_results={
            "q1": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}]
        },
        pages={"https://example.com/a": "unique-private-body-marker"},
        model_gateway=model,
    )
    checkpointer = InMemorySaver()

    result = await _run_workflow(model, fixture, checkpointer=checkpointer)

    assert result["outcome"].termination_reason == "completed"
    snapshot = await build_workflow_research_graph(
        build_research_agent_graph(), checkpointer=checkpointer
    ).aget_state({"configurable": {"thread_id": "workflow-thread"}})
    assert "search_result" not in snapshot.values
    serialized = json.dumps(snapshot.values, default=str, ensure_ascii=False)
    assert "unique-private-body-marker" not in serialized


class _UnfinishedPlanTopicGraph:
    """Delegates to the real topic graph but reports an open plan item."""

    def __init__(self, inner) -> None:
        self._inner = inner

    async def ainvoke(self, input_data, config=None, **kwargs):
        raw = await self._inner.ainvoke(input_data, config=config, **kwargs)
        outcome = raw["outcome"].model_copy(
            update={
                "plan_total": 2,
                "plan_completed": 1,
                "unfinished_todos": ["尚未完成的步骤"],
            }
        )
        return {"outcome": outcome}


@pytest.mark.asyncio
async def test_unfinished_executor_plan_downgrades_completed_to_incomplete() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": lambda prompt: _evaluation_with_prompt_evidence(
                prompt, sufficient=True
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
    topic = _UnfinishedPlanTopicGraph(build_research_agent_graph())

    result = await _run_workflow(model, fixture, topic_graph=topic)
    outcome = result["outcome"]

    assert outcome.evidence_ids
    assert outcome.termination_reason == "incomplete_plan"
