"""Independent strategies recover by reading before spending on new searches."""

import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ResearchRequirement, ResearchTopicOutcome
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.strategies.multi_agent.graph import build_multi_agent_research_graph
from deeptrace.strategies.plan_execute.graph import build_plan_execute_research_graph
from strategies.fixtures import build_gateway_fixture, evaluation_payload_from_view
from strategies.workflow.test_reread import RereadModel
from strategies.workflow.test_graph import _research_input
from strategies.test_reference_materials import seed










class StrategyRereadModel(RereadModel):
    def __init__(self, *, resolves, multi_agent):
        super().__init__(resolves=resolves)
        self.multi_agent = multi_agent
        payload = json.dumps({
            ("assignments" if multi_agent else "queries"): ["initial official"],
            "query_targets": {"initial official": ["r1", "r2"]},
            "requirements": [
                {"id": "r1", "description": "ordinary execution"},
                {"id": "r2", "description": "restart requirements"},
            ],
        })
        self._responses.update(planner=payload, supervisor=payload, follow_up=self.replan)

    def evaluate(self, prompt):
        self.evaluations += 1
        complete = self.resolves and self.evaluations > 1 and "REREAD_FACT" in prompt
        action = "complete" if complete else "follow_up" if self.multi_agent else "replan"
        result = evaluation_payload_from_view(prompt, action=action)
        result["coverage"]["items"][0].update(status="covered", finding_ids=["finding-1"])
        return json.dumps(result)
