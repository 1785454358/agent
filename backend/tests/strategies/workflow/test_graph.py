from __future__ import annotations

import json
import re
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ResearchInput, ResearchMode
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.topic import build_research_topic_graph
from deeptrace.strategies.workflow.graph import build_workflow_research_graph

from strategies.fixtures import build_gateway_fixture


class ScriptedModelGateway:
    """Records role calls and returns scripted text or callable responses."""

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
    topic_graph = topic_graph or build_research_topic_graph()
    graph = build_workflow_research_graph(
        topic_graph, query_limit=query_limit, checkpointer=checkpointer
    )
    config = (
        {"configurable": {"thread_id": "workflow-thread"}} if checkpointer else None
    )
    result = await graph.ainvoke(
        {"research_input": _research_input(question)},
        config=config,
        context=fixture.context,
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

    assert [role for role, _prompt in model.calls] == ["planner", "evaluator"]
    assert result["queries"] == ["query one", "query two"]
    assert outcome.mode is ResearchMode.WORKFLOW
    assert outcome.termination_reason == "completed"
    assert len(outcome.evidence_ids) == 2
    assert len(outcome.findings) == 1
    assert set(outcome.findings[0].evidence_ids) <= set(outcome.evidence_ids)
    assert outcome.unresolved_gaps == []
    assert outcome.executed_steps == 6


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
            "planner": json.dumps(
                {"queries": ["q1", "q1", "q2", "q3", "q4", "q5"]}
            ),
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
    assert any(
        "doomed query" in gap and "no_search_results" in gap
        for gap in outcome.unresolved_gaps
    )
    assert outcome.termination_reason == "completed"


@pytest.mark.asyncio
async def test_zero_usable_evidence_yields_partial_no_sources() -> None:
    model = ScriptedModelGateway(
        {
            "planner": json.dumps({"queries": ["q1"]}),
            "evaluator": "evaluator must not run",
        }
    )
    fixture = build_gateway_fixture(
        default_search_results=[], model_gateway=model
    )

    result = await _run_workflow(model, fixture)
    outcome = result["outcome"]

    assert outcome.evidence_ids == []
    assert outcome.findings == []
    assert outcome.termination_reason == "no_sources"
    assert [role for role, _prompt in model.calls] == ["planner"]


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
    flaky = FlakyTopicGraph(build_research_topic_graph(), fail_query="broken")

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
        build_research_topic_graph(), checkpointer=checkpointer
    ).aget_state({"configurable": {"thread_id": "workflow-thread"}})
    assert "search_result" not in snapshot.values
    serialized = json.dumps(snapshot.values, default=str, ensure_ascii=False)
    assert "unique-private-body-marker" not in serialized
