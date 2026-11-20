"""A successful bounded reassessment cannot erase unseen verified work."""

import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from deeptrace.domain import CoverageAssessment, EvidenceSupport, Finding, ResearchRequirement, ResearchTopicOutcome
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.research.quality import evaluate_node
from deeptrace.research.verification import project_verification_result
from research.test_runtime import request
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["omitted", "changed", "rejected"])
async def test_bounded_reassessment_preserves_valid_unseen_claim_without_reusing_coverage(scenario, monkeypatch):
    # Exercise retention independently of the evaluator's default source cap.
    # A deliberately narrow view simulates a context window omitting old work.
    import deeptrace.strategies.evidence_evaluation as evaluation
    assemble = evaluation.assemble_reference_evaluation_view

    async def narrow_view(*args, **kwargs):
        kwargs["evidence_ids"] = kwargs["evidence_ids"][:8]
        return await assemble(*args, **kwargs)

    monkeypatch.setattr(evaluation, "assemble_reference_evaluation_view", narrow_view)
    old_body, new_body = "Dated room reference is 300 for two guests.", "Ticket admission costs 40."

    class Assessor:
        async def invoke(self, *, messages, **kwargs):
            view = json.loads(str(messages[-1].content).split("EVIDENCE_VIEW_JSON:\n", 1)[1])
            ref = next(p["ref"] for p in view["passages"] if p["text"] == new_body)
            return AIMessage(content=json.dumps({
                "findings": [{"id": "f1", "claim": new_body, "confidence": 0.9, "supports": [{"ref": ref}]}],
                "source_checks": [{"source": s["source"], "status": "ineligible"
                    if scenario == "rejected" and s["url"].endswith("material-8") else "eligible",
                    "reason": "Withdrawn reference" if s["url"].endswith("material-8") else "Original text"}
                    for s in view["sources"]],
                "coverage": {"items": [
                    {"requirement_id": "r1", "status": "covered", "reason": "Ticket supported", "finding_ids": ["f1"]},
                    {"requirement_id": "r2", "status": "missing", "reason": "Room not assessed", "finding_ids": []},
                ]}, "sufficient": False, "unresolved_gaps": [],
            }))

    fixture = build_gateway_fixture(model_gateway=Assessor())
    records = [await seed(fixture, i, new_body if i == 0 else f"Other material {i}.") for i in range(8)]
    old = await seed(fixture, 8, old_body)
    requirements = [ResearchRequirement(id="r1", description="Ticket price"),
                    ResearchRequirement(id="r2", description="Dated room reference")]
    prior = Finding(id="f1", claim=old_body, evidence_ids=[old.id], confidence=0.9,
        supports=[EvidenceSupport(evidence_id=old.id, version=old.version, content_hash=old.content_hash,
                                  start=0, end=len(old_body), quote=old_body)])
    verification = project_verification_result(evidence=[old], bodies={old.id: old_body}, findings=[prior],
        source_eligibility={old.id: "eligible"}, requirements=requirements,
        coverage=CoverageAssessment(items=[
            {"requirement_id": "r1", "status": "missing", "reason": "No ticket"},
            {"requirement_id": "r2", "status": "covered", "reason": "Room known", "finding_ids": ["f1"]},
        ]))
    if scenario == "changed":
        await seed(fixture, 8, "Corrected room reference; former price withdrawn.")
    if scenario == "rejected":
        records = [old, *records]
    else:
        records.append(old)  # Deliberately outside this test's narrowed view.
    anchors = [ReadEvidenceAnchor(evidence_id=r.id, version=r.version, content_hash=r.content_hash,
        start=0, end=len(await fixture.evidence_store.read_body(fixture.context.workspace_id, r.id))) for r in records]
    result = await evaluate_node({
        **request().model_dump(), "requirements": requirements, "evidence_contract_version": 3,
        "evidence_ids": [r.id for r in records], "findings": [prior], "verification": verification,
        "source_eligibility": {old.id: "eligible"}, "coverage": verification.coverage,
        "topic_outcomes": [ResearchTopicOutcome(query="ticket", evidence_ids=[r.id for r in records], read_anchors=anchors)],
    }, Runtime(context=fixture.context))
    claims = [f.claim for f in result["findings"]]
    assert new_body in claims
    assert (old_body in claims) is (scenario == "omitted")
    assert len({f.id for f in result["findings"]}) == len(claims)
    assert result["evaluation"] is not None
    assert result["coverage"].items[1].status == "missing"
    assert not result["verification"].coverage_complete


@pytest.mark.asyncio
async def test_controller_discards_rejected_support_without_reassessing_the_same_material():
    class Assessor:
        calls = 0

        async def invoke(self, *, messages, **kwargs):
            self.calls += 1
            view = json.loads(str(messages[-1].content).split("EVIDENCE_VIEW_JSON:\n", 1)[1])
            return AIMessage(content=json.dumps({
                "findings": [{"id": "f1", "claim": "Marketing price", "confidence": 0.8,
                              "supports": [{"ref": view["passages"][0]["ref"]}]}],
                "source_checks": [{"source": "s1", "status": "ineligible", "basis": "reliability",
                                   "reason": "An unsupported advertisement"}],
                "coverage": {"items": [{"requirement_id": "r1", "status": "covered",
                    "reason": "A claimed price", "finding_ids": ["f1"]}]},
                "sufficient": True, "unresolved_gaps": [],
            }))

    model = Assessor()
    fixture = build_gateway_fixture(model_gateway=model)
    body = "Marketing price without independent conditions."
    record = await seed(fixture, 1, body)
    result = await evaluate_node({
        **request().model_dump(), "requirements": [ResearchRequirement(id="r1", description="Price")],
        "evidence_contract_version": 3, "evidence_ids": [record.id],
        "topic_outcomes": [ResearchTopicOutcome(query="price", evidence_ids=[record.id], read_anchors=[
            ReadEvidenceAnchor(evidence_id=record.id, version=record.version,
                content_hash=record.content_hash, start=0, end=len(body))])],
    }, Runtime(context=fixture.context))
    assert model.calls == 1
    assert result["findings"] == []
    assert result["coverage"].items[0].status == "missing"
    assert not result["evaluation"].sufficient
    assert not result["verification"].accepted_claims


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', [False, True])
async def test_later_schema_failure_preserves_valid_source_admission_even_without_accepted_claims(changed):
    class BrokenAssessment:
        async def invoke(self, **kwargs):
            return AIMessage(content='not valid JSON')

    fixture = build_gateway_fixture(model_gateway=BrokenAssessment())
    body = 'The original report describes a setup, without enough data for a ranking.'
    record = await seed(fixture, 1, body)
    requirements = [ResearchRequirement(id='r1', description='Can the report establish a ranking?')]
    coverage = CoverageAssessment(items=[{'requirement_id': 'r1', 'status': 'missing', 'reason': 'No measurements'}])
    previous = project_verification_result(evidence=[record], bodies={record.id: body}, findings=[],
        source_eligibility={record.id: 'eligible'}, requirements=requirements, coverage=coverage)
    if changed:
        await seed(fixture, 1, 'The report was corrected and withdrawn.')
    result = await evaluate_node({
        **request().model_dump(), 'requirements': requirements, 'evidence_contract_version': 3,
        'evidence_ids': [record.id], 'findings': [], 'verification': previous,
        'source_eligibility': {record.id: 'eligible'}, 'coverage': coverage,
        'topic_outcomes': [ResearchTopicOutcome(query='report', evidence_ids=[record.id], read_anchors=[
            ReadEvidenceAnchor(evidence_id=record.id, version=record.version, content_hash=record.content_hash,
                               start=0, end=len(body))])],
    }, Runtime(context=fixture.context))
    assert (result['source_eligibility'][record.id] == 'eligible') is (not changed)
    assert result['evaluation'] is None
    assert not result['verification'].coverage_complete
    assert not result['verification'].accepted_claims
