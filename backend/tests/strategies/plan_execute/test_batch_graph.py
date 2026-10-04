import json

import pytest
from langchain_core.messages import AIMessage

from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.model_budget import ModelBudgetExceeded
from deeptrace.harness.model_gateway import ModelCallError
from deeptrace.domain import ErrorCategory
from deeptrace.strategies.plan_execute.graph import build_plan_execute_research_graph
from harness.test_batch_research import BatchModel
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


@pytest.mark.asyncio
async def test_empty_initial_batch_can_replan_and_collect_missing_evidence():
    model = GapModel()
    fixture = build_gateway_fixture(model_gateway=model, search_results={"gap-query": [
        {"url": "https://example.com/gap", "title": "fact", "snippet": "target fact"}]},
        pages={"https://example.com/gap": "target fact is supported."})
    graph = build_plan_execute_research_graph(build_batch_research_graph())
    result = await graph.ainvoke(_research_input("研究 target fact"), context=fixture.context)
    assert fixture.search.calls == ["initial", "gap-query"]
    assert result["replan_count"] == 1
    assert result["outcome"].termination_reason == "completed"
    assert result["outcome"].findings[0].supports
    assert [role for role, _, _ in model.calls] == ["planner", "replanner", "researcher", "evaluator"]


@pytest.mark.asyncio
async def test_research_with_no_new_evidence_stops_after_one_unproductive_supplement():
    model = GapModel()
    fixture = build_gateway_fixture(model_gateway=model)
    graph = build_plan_execute_research_graph(build_batch_research_graph())
    result = await graph.ainvoke(_research_input("研究 target fact"), context=fixture.context)
    assert fixture.search.calls == ["initial", "gap-query"]
    assert result["replan_count"] == 1
    assert result["outcome"].termination_reason == "no_research_progress"
    assert [role for role, _, _ in model.calls] == ["planner", "replanner"]


@pytest.mark.asyncio
async def test_evaluation_budget_denial_preserves_acquired_evidence_and_finishes():
    class BudgetModel(GapModel):
        async def invoke(self, **kwargs):
            if kwargs["role"] == "evaluator":
                raise ModelBudgetExceeded("input_tokens")
            return await super().invoke(**kwargs)
    fixture = build_gateway_fixture(model_gateway=BudgetModel(), search_results={"initial": [
        {"url": "https://example.com/a", "title": "fact", "snippet": "target fact"}]})
    graph = build_plan_execute_research_graph(build_batch_research_graph())
    result = await graph.ainvoke(_research_input("研究 target fact"), context=fixture.context)
    assert len(result["outcome"].evidence_ids) == 1
    assert result["outcome"].termination_reason == "insufficient_evidence"
    assert "evaluation_budget_exhausted" in result["diagnostic_gaps"]


@pytest.mark.asyncio
async def test_evaluation_transport_failure_preserves_evidence_without_false_coverage():
    class TimeoutModel(GapModel):
        async def invoke(self, **kwargs):
            if kwargs["role"] == "evaluator":
                raise ModelCallError(ErrorCategory.TRANSIENT)
            return await super().invoke(**kwargs)

    fixture = build_gateway_fixture(model_gateway=TimeoutModel(), search_results={"initial": [
        {"url": "https://example.com/a", "title": "fact", "snippet": "target fact"}]})
    graph = build_plan_execute_research_graph(build_batch_research_graph())
    result = await graph.ainvoke(_research_input("研究 target fact"), context=fixture.context)
    assert len(result["outcome"].evidence_ids) == 1
    assert result["outcome"].termination_reason == "insufficient_evidence"
    assert all(item.status == "missing" for item in result["coverage"].items)
    assert "evaluation_transport_failure" in result["diagnostic_gaps"]


@pytest.mark.asyncio
async def test_evaluator_repairs_too_many_supports_once_without_repeating_acquisition():
    class RepairModel(GapModel):
        def __init__(self):
            super().__init__()
            self.evaluations = 0

        async def invoke(self, **kwargs):
            response = await super().invoke(**kwargs)
            if kwargs["role"] == "evaluator":
                self.evaluations += 1
                if self.evaluations == 1:
                    payload = json.loads(response.content)
                    payload["findings"][0]["supports"] *= 4
                    return AIMessage(content=json.dumps(payload))
            return response

    model = RepairModel()
    fixture = build_gateway_fixture(model_gateway=model, search_results={"initial": [
        {"url": "https://example.com/a", "title": "fact", "snippet": "target fact"}]})
    result = await build_plan_execute_research_graph(build_batch_research_graph()).ainvoke(
        _research_input("研究 target fact"), context=fixture.context)
    assert result["outcome"].termination_reason == "completed"
    assert model.evaluations == 2
    assert fixture.search.calls == ["initial"]
    assert fixture.fetcher.calls == ["https://example.com/a"]


@pytest.mark.asyncio
async def test_supplement_sources_reach_evaluator_when_the_old_pool_has_eight_sources():
    from deeptrace.domain import ResearchRequirement, ResearchTopicOutcome
    from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
    from deeptrace.strategies.plan_execute.models import ReferenceExecutorDecision
    from strategies.test_reference_materials import seed

    model = GapModel()
    fixture = build_gateway_fixture(model_gateway=model)
    records = [await seed(fixture, i, f"fact {i}") for i in range(9)]
    state = {**_research_input("fact"), "evidence_contract_version": 3,
        "requirements": [ResearchRequirement(id="r1", description="fact")],
        "evidence_ids": [r.id for r in records],
        "topic_outcomes": [ResearchTopicOutcome(query="gap-query", evidence_ids=[records[-1].id])],
        "supplement_targets": {"gap-query": ["r1"]}}
    await run_evidence_evaluation(state, fixture.context, ReferenceExecutorDecision)
    prompt = str(model.calls[-1][1][-1].content)
    assert records[-1].canonical_url in prompt
    assert '"text":"fact 8"' in prompt
