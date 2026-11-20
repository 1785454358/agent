"""A cited solution cannot complete without checking its cross-step constraints."""

import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import CoverageAssessment, EvidenceSupport, Finding, ResearchRequirement
from deeptrace.domain.delivery import DeliveryPlan
from deeptrace.responses.graph import build_answer_graph
from responses.test_supported_findings import _case
from responses.test_graph import _seed_evidence


async def solution_case():
    payload, _, fixture, _ = await _case()
    body = "The three-day city metro pass costs 40 and excludes the remote railway. The remote return fare is 50."
    ids = await _seed_evidence(fixture.evidence_store, [("https://example.com/fares", "Fare conditions", body)])
    record = await fixture.evidence_store.get(fixture.context.workspace_id, ids[0])
    plan = DeliveryPlan(approach="City visit and remote railway return",
        assumptions=["One adult"], outline=["City visit using metro", "Remote railway return"],
        evidence_needs=[{"requirement_id": "r1", "query": "fares and pass coverage"}],
        consistency_checks=["Transport budget includes every route leg", "Total uses the same occupancy"])
    payload.active_evidence_ids = ids
    payload.research_outcome = payload.research_outcome.model_copy(update={
        "delivery_plan": plan, "evidence_ids": ids,
        "requirements": [ResearchRequirement(id="r1", description="Transport fares and coverage")],
        "findings": [Finding(id="f1", claim=body, confidence=0.9, evidence_ids=ids,
            supports=[EvidenceSupport(evidence_id=record.id, version=record.version,
                content_hash=record.content_hash, start=0, end=len(body), quote=body)])],
        "coverage": CoverageAssessment(items=[{"requirement_id": "r1", "status": "covered",
            "reason": "Fares and exclusions available", "finding_ids": ["f1"]}]),
    })
    return payload, fixture


class SolutionReviewer:
    def __init__(self, *, defect=None, unresolved=False):
        self.calls = []
        self.defect, self.unresolved = defect, unresolved

    async def invoke(self, *, messages, **kwargs):
        prompt = "\n".join(str(m.content) for m in messages)
        self.calls.append(prompt)
        if "ANSWER_REVIEW_JSON:" not in prompt:
            return AIMessage(content=json.dumps({"content": "全部交通只需40元 [1]。"}))
        checks = [{"check_id": "c1", "status": "unresolved" if self.unresolved else "passed",
                   "reason": "远郊往返尚未纳入预算" if self.unresolved else "地铁40加远郊往返50，共90"},
                  {"check_id": "c2", "status": "passed", "reason": "均按1名成人"}]
        if self.defect == "missing":
            checks.pop()
        elif self.defect == "duplicate":
            checks[1]["check_id"] = "c1"
        elif self.defect == "unknown":
            checks[1]["check_id"] = "c6"
        return AIMessage(content=json.dumps({
            "content": "远郊往返尚未纳入预算，不能承诺总交通40元 [1]。" if self.unresolved
            else "地铁票40元不含远郊铁路；加往返50元，合计90元 [1]。",
            "issues": ["票种不覆盖完整路线"], "unanswered_points": [], "consistency_checks": checks,
        }))


@pytest.mark.asyncio
async def test_solution_and_actual_dependencies_reach_writer_and_existing_review():
    payload, fixture = await solution_case()
    model = SolutionReviewer()
    result = await build_answer_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=True))
    assert "90元" in result["outcome"].content
    assert result["outcome"].partial_reason is None
    assert "City visit and remote railway return" in model.calls[0]
    review = json.loads(model.calls[1].split("ANSWER_REVIEW_JSON:\n", 1)[1])
    assert review["delivery_plan"]["outline"] == ["City visit using metro", "Remote railway return"]
    assert review["consistency_checks"] == {
        "c1": "Transport budget includes every route leg", "c2": "Total uses the same occupancy"}
    assert len(model.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["missing", "duplicate", "unknown"])
async def test_skipped_or_invented_consistency_checks_cannot_complete(defect):
    payload, fixture = await solution_case()
    model = SolutionReviewer(defect=defect)
    result = await build_answer_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=True))
    assert result["outcome"].partial_reason == "answer_review_unavailable"
    assert len(model.calls) == 3  # existing single repair, no new review phase


@pytest.mark.asyncio
async def test_unresolved_route_dependency_stays_partial_even_with_valid_citations():
    payload, fixture = await solution_case()
    model = SolutionReviewer(unresolved=True)
    result = await build_answer_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=True))
    assert "尚未纳入预算" in result["outcome"].content
    assert result["outcome"].partial_reason == "answer_consistency_incomplete"
    assert result["outcome"].citations


@pytest.mark.asyncio
async def test_disabled_review_never_labels_a_solution_as_consistency_checked():
    payload, fixture = await solution_case()
    model = SolutionReviewer()
    result = await build_answer_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=False))
    assert result["outcome"].partial_reason == "answer_consistency_unchecked"
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_small_solution_review_fits_remaining_window_without_unrelated_review_rules():
    from deeptrace.responses.fact_review import review_answer

    payload, fixture = await solution_case()
    model = SolutionReviewer()
    reviewed = await review_answer(replace(fixture.context, model_gateway=model),
        question="Plan the city and remote railway visits within 100 per person",
        constraints=["One adult"], content="全部交通只需40元 [1]。",
        sources=["[1] The city pass costs 40 and excludes remote rail. Remote return costs 50."],
        input_budget=1800, delivery_plan=payload.research_outcome.delivery_plan)
    assert "90元" in reviewed.content
    assert len(model.calls) == 1
