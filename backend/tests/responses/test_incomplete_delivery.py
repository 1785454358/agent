"""Eligible original text remains usable when no candidate claim is accepted."""

from dataclasses import replace
import json

import pytest

from deeptrace.domain import CoverageAssessment, Finding, ResearchRequirement
from deeptrace.responses.graph import build_answer_graph
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from responses.test_graph import ScriptedModelGateway, _response_input, _seed_evidence
from strategies.fixtures import build_gateway_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize("limited_budget", [False, True])
async def test_no_accepted_claims_still_explains_what_original_material_can_support(limited_budget):
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(store, [
        ("https://example.com/structured", "Structured output",
         "ProviderStrategy uses native structured output. ToolStrategy uses tool calling. "
         "Latency and billing depend on the provider and workload."),
        ("https://example.com/rejected", "Rejected", "UNSUITABLE_SOURCE_SECRET"),
    ])
    answer = "当前材料不足以判断通用最低费用策略。资料仅说明两种实现方式，延迟和费用取决于供应商与负载 [1]。需在同一模型、输入和任务集上测量。"

    class Model(ScriptedModelGateway):
        async def available_input_tokens(self, role):
            return 5000 if limited_budget else 100000

    model = Model({"responder": json.dumps({"content": answer, "unanswered_points": ["缺少成本测量"]})})
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    payload = _response_input(ids, question="Which strategy is universally cheapest and fastest?")
    payload.verified_finding_ids = []
    payload.research_outcome = payload.research_outcome.model_copy(update={
        "evidence_contract_version": 3,
        "findings": [Finding(id="rejected", claim="FORGED_UNVERIFIED_CLAIM", evidence_ids=[ids[0]], confidence=0.9)],
        "requirements": [ResearchRequirement(id="r1", description="Determine cost and latency")],
        "coverage": CoverageAssessment(items=[{
            "requirement_id": "r1", "status": "missing", "reason": "No measurements", "finding_ids": [],
        }]),
        "source_eligibility": {ids[0]: "eligible", ids[1]: "ineligible"},
        "termination_reason": "insufficient_evidence",
    })
    result = await build_answer_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, response_fact_review=True,
    ))
    outcome = result["outcome"]
    assert outcome.content == answer
    assert outcome.cited_evidence_ids == [ids[0]]
    assert outcome.partial_reason == "insufficient_evidence"
    assert len(model.calls) == 2
    assert all("Latency and billing depend" in prompt for _, prompt in model.calls)
    assert all("UNSUITABLE_SOURCE_SECRET" not in prompt for _, prompt in model.calls)
    assert all("FORGED_UNVERIFIED_CLAIM" not in prompt for _, prompt in model.calls)
