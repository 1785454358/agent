import json

import pytest
from harness.test_batch_research import BatchModel
from langchain_core.messages import AIMessage

from deeptrace.domain import ErrorCategory
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.model_budget import ModelBudgetExceeded
from deeptrace.harness.model_gateway import ModelCallError
from deeptrace.strategies.plan_execute.graph import build_plan_execute_research_graph
from strategies.fixtures import build_gateway_fixture, evaluation_payload_from_view
from strategies.plan_execute.test_graph import _research_input


class GapModel(BatchModel):
    async def invoke(self, *, role, messages, tools=None):
        if role == "researcher":
            return await super().invoke(role=role, messages=messages, tools=tools)
        self.calls.append((role, messages, tools))
        if role == "planner":
            return AIMessage(content=json.dumps({"queries": ["initial"],
                "requirements": [{"id": "r1", "description": "target fact"}],
                "query_targets": {"initial": ["r1"]}}))
        if role == "replanner":
            return AIMessage(content=json.dumps({"tasks": [{"query": "gap-query", "target_requirement_ids": ["r1"]}]}))
        if role == "evaluator":
            return AIMessage(content=json.dumps(evaluation_payload_from_view(str(messages[-1].content))))
        raise AssertionError(role)
