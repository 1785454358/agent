"""Workflow can recover actual missing evidence once, under the sealed contract."""

import json

import pytest
from harness.test_batch_research import BatchModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.strategies.workflow.graph import build_workflow_research_graph
from deeptrace.strategies.workflow.nodes import build_plan_queries_node
from strategies.fixtures import (
    ScriptedModelGateway,
    build_gateway_fixture,
    evaluation_payload_from_view,
)
from strategies.workflow.test_graph import _research_input


class RecoveryModel(ScriptedModelGateway):
    def __init__(self, *, resolves=True, complete=False, tasks=None, exhaust=False):
        self.evaluations = 0
        self.research_exhausted = False
        self.resolves = resolves
        self.complete = complete
        self.exhaust = exhaust
        self.seen_recovery = []
        self.branch_model = BatchModel()
        tasks = tasks if tasks is not None else [
            {"query": "restart official", "target_requirement_ids": ["r2"]},
        ]
        super().__init__({
            "planner": json.dumps({
                "queries": ["initial official"],
                "requirements": [
                    {"id": "r1", "description": "initial execution"},
                    {"id": "r2", "description": "restart recovery"},
                ],
                "query_targets": {"initial official": ["r1", "r2"]},
            }),
            "replanner": json.dumps({"tasks": tasks}),
            "evaluator": self.evaluate,
        })

    async def invoke(self, *, role, messages, tools=None):
        if role == "researcher":
            self.calls.append((role, str(messages[-1].content)))
            return await self.branch_model.invoke(role=role, messages=messages, tools=tools)
        return await super().invoke(role=role, messages=messages, tools=tools)

    def evaluate(self, prompt):
        self.evaluations += 1
        has_recovery = "RECOVERY_FACT" in prompt
        self.seen_recovery.append(has_recovery)
        complete = self.complete or (has_recovery and self.resolves)
        payload = evaluation_payload_from_view(prompt, sufficient=complete)
        first = payload["coverage"]["items"][0]
        first.update(status="covered", finding_ids=["finding-1"], reason="initial source read")
        self.research_exhausted = self.exhaust
        return json.dumps(payload)


async def run_case(model, *, checkpointer=None):
    fixture = build_gateway_fixture(
        model_gateway=model,
        search_results={
            "initial official": [{"url": "https://example.com/initial", "title": "Initial"}],
            "restart official": [{"url": "https://example.com/restart", "title": "Restart"}],
            "restart alternate": [{"url": "https://example.com/alternate", "title": "Alternate"}],
        }, default_search_results=[],
        pages={
            "https://example.com/initial": "INITIAL_FACT: ordinary execution is documented.",
            "https://example.com/restart": "RECOVERY_FACT: restart requires durable storage; initial execution is documented.",
            "https://example.com/alternate": "RECOVERY_FACT: another official recovery detail is documented.",
        },
    )
    graph = build_workflow_research_graph(build_batch_research_graph(), checkpointer=checkpointer)
    result = await graph.ainvoke(
        _research_input("Compare ordinary execution and restart requirements"),
        config={"configurable": {"thread_id": "recover-thread"}} if checkpointer else None,
        context=fixture.context,
    )
    return result, fixture
