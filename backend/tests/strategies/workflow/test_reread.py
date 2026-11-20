"""Workflow rereads before dispatching deferred fresh searches."""

import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.strategies.workflow.graph import build_workflow_research_graph
from deeptrace.strategies.workflow.nodes import build_plan_queries_node
from strategies.fixtures import build_gateway_fixture, evaluation_payload_from_view
from strategies.workflow.test_graph import _research_input
from strategies.workflow.test_recovery import RecoveryModel


class RereadModel(RecoveryModel):
    def __init__(self, *, resolves=True, fallback=True):
        super().__init__(resolves=resolves)
        self._responses["replanner"] = self.replan
        self.fallback = fallback

    def replan(self, prompt):
        data = json.loads(prompt.split("补查上下文：", 1)[1])
        blocks = data.get("source_outline", [])
        chosen = next((b for b in blocks if "REREAD_FACT" in b["preview"]), None)
        return json.dumps(
            {
                "reads": (
                    [{"block_id": chosen["block_id"], "target_requirement_ids": ["r2"]}]
                    if chosen
                    else []
                ),
                "tasks": (
                    [{"query": "restart official", "target_requirement_ids": ["r2"]}]
                    if self.fallback or not blocks
                    else []
                ),
            }
        )

    def evaluate(self, prompt):
        self.evaluations += 1
        self.seen_recovery.append("REREAD_FACT" in prompt)
        complete = self.resolves and self.evaluations > 1 and "REREAD_FACT" in prompt
        payload = evaluation_payload_from_view(prompt, sufficient=complete)
        payload["coverage"]["items"][0].update(
            status="covered", finding_ids=["finding-1"], reason="ordinary fact"
        )
        return json.dumps(payload)


async def run_reread(model, *, interrupt=False, graph_factory=build_workflow_research_graph):
    fixture = build_gateway_fixture(
        model_gateway=model,
        search_results={
            "initial official": [
                {"url": "https://example.com/initial", "title": "Initial"}
            ],
            "restart official": [
                {"url": "https://example.com/restart", "title": "Restart"}
            ],
        },
        default_search_results=[],
        pages={
            "https://example.com/initial": "INITIAL_FACT ordinary execution.\n\n"
            + "Ordinary initial execution details. " * 180
            + "\n\nREREAD_FACT: durable storage is mandatory.",
            "https://example.com/restart": "A fresh alternative source.",
        },
    )
    graph = graph_factory(
        build_batch_research_graph(), checkpointer=InMemorySaver()
    )
    result = await graph.ainvoke(
        _research_input("Compare ordinary execution and restart requirements"),
        config={"configurable": {"thread_id": "reread-thread"}},
        context=fixture.context,
        interrupt_after=["recover"] if interrupt else None,
    )
    if interrupt:
        return result, fixture, graph
    return result, fixture
