"""Repeatable research-mode comparison on a scripted dataset (no real API).

Computes deterministic quality/cost/latency proxies for the three research
strategies over the same question set, satisfying the Plan 8 requirement for
a repeatable baseline. Real-provider evaluation runs via the `real` marker.
"""

from __future__ import annotations

import json
import re

from langgraph.checkpoint.memory import InMemorySaver

import pytest

from deeptrace.domain import ResearchMode
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.responses import build_answer_graph
from deeptrace.strategies import (
    build_multi_agent_research_graph,
    build_plan_execute_research_graph,
    build_research_topic_graph,
    build_workflow_research_graph,
)

from strategies.fixtures import build_gateway_fixture


QUESTION = "LangGraph Harness 的 checkpoint 与恢复机制"
SEARCH_RESULTS = {
    QUESTION: [
        {"url": "https://example.com/a", "title": "A", "snippet": "checkpoint"}
    ]
}


def _evaluation(prompt: str) -> str:
    ids = sorted(set(re.findall(r"evidence-[0-9a-f]+", prompt)))
    return json.dumps(
        {
            "findings": [
                {
                    "id": "finding-1",
                    "claim": "checkpoint 支持恢复",
                    "evidence_ids": ids[:1],
                    "confidence": 0.9,
                }
            ],
            "unresolved_gaps": [],
            "sufficient": True,
        }
    )


def _evaluate_mode(mode: ResearchMode) -> dict[str, object]:
    import asyncio

    model_calls: list[str] = []

    class Gateway:
        async def invoke(self, *, role: str, messages: list[Any]) -> Any:
            model_calls.append(role)
            prompt = str(messages[-1].content)
            if role == "planner":
                return json.dumps({"queries": [QUESTION]})
            if role == "supervisor":
                return json.dumps({"assignments": [QUESTION]})
            if role == "evaluator":
                if "action" in prompt:
                    ids = sorted(set(re.findall(r"evidence-[0-9a-f]+", prompt)))
                    return json.dumps(
                        {
                            "action": "complete",
                            "reason": "资料充足",
                            "findings": [
                                {
                                    "id": "finding-1",
                                    "claim": "checkpoint 支持恢复",
                                    "evidence_ids": ids[:1],
                                    "confidence": 0.9,
                                }
                            ],
                            "unresolved_gaps": [],
                        }
                    )
                return _evaluation(prompt)
            return json.dumps({"content": "结论 [1]。"})

    fixture = build_gateway_fixture(
        search_results=SEARCH_RESULTS,
        pages={"https://example.com/a": "body-a"},
        model_gateway=Gateway(),
    )
    strategies = StrategyRegistry()
    builders = {
        ResearchMode.WORKFLOW: build_workflow_research_graph,
        ResearchMode.PLAN_EXECUTE: build_plan_execute_research_graph,
        ResearchMode.MULTI_AGENT: build_multi_agent_research_graph,
    }
    strategies.register(
        StrategyRegistration(
            mode,
            builders[mode](build_research_topic_graph()),
        )
    )
    responses = ResponseGraphRegistry()
    responses.register(
        ResponseRegistration(_answer_mode(), build_answer_graph())
    )
    graph = build_agent_runtime_graph(
        strategies,
        responses,
        checkpointer=InMemorySaver(
            serde=create_harness_checkpoint_serializer()
        ),
    )

    from deeptrace.harness.state import new_conversation, new_turn
    from deeptrace.application.research import ApplicationResearchRequest, ResearchApplicationService

    service = ResearchApplicationService(graph)
    outcome = asyncio.run(
        service.invoke(
            ApplicationResearchRequest(
                run_id="run-1",
                thread_id="thread-1",
                question=QUESTION,
                mode=mode,
            ),
            config={"configurable": {"thread_id": "thread-1"}},
            context=fixture.context,
        )
    )
    snapshot = asyncio.run(graph.aget_state({"configurable": {"thread_id": "thread-1"}}))
    research = snapshot.values["turn"]["research_outcome"]
    return {
        "mode": mode.value,
        "termination": research.termination_reason,
        "evidence_count": len(research.evidence_ids),
        "executed_steps": research.executed_steps,
        "model_calls": len(model_calls),
        "tool_calls": len(fixture.gateway.calls),
        "answered": outcome.partial_reason is None,
    }


def _answer_mode():
    from deeptrace.domain import ResponseMode

    return ResponseMode.ANSWER


def test_three_modes_complete_on_the_same_dataset_with_comparable_cost() -> None:
    rows = [_evaluate_mode(mode) for mode in ResearchMode]

    print("=== Research mode baseline (scripted dataset) ===")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))

    failures = [row for row in rows if row["termination"] != "completed"]
    if failures:
        print("non-completed rows:", failures)

    assert all(row["termination"] == "completed" for row in rows)
    assert all(row["answered"] for row in rows)
    assert all(row["evidence_count"] == 1 for row in rows)
    # cost/latency proxies stay within a deterministic, documented envelope
    workflow_row = next(r for r in rows if r["mode"] == "workflow")
    assert workflow_row["executed_steps"] <= 8
    plan_row = next(r for r in rows if r["mode"] == "plan_execute")
    assert plan_row["executed_steps"] <= 10
    multi_row = next(r for r in rows if r["mode"] == "multi_agent")
    assert multi_row["executed_steps"] <= 10

    print("\n=== Research mode baseline (scripted dataset) ===")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
