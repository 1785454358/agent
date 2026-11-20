import pytest

from deeptrace.domain import CoverageAssessment, EvidenceSupport, Finding, ResearchRequirement
from deeptrace.strategies.evidence_evaluation import coverage_complete, normalize_coverage, seal_requirements


def finding():
    return Finding(id="f1",claim="A checked source",evidence_ids=["paper"],confidence=0.9,
        supports=[EvidenceSupport(evidence_id="paper",version=1,content_hash="sha256:a",
            start=0,end=22,quote="A measured experiment.")])


@pytest.mark.parametrize("allowed,checked,expected",[(True,True,"covered"),(True,False,"missing"),(False,True,"missing")])
def test_unknown_requires_user_permission_and_actual_checked_scope(allowed,checked,expected):
    req=ResearchRequirement(id="r1",description="计算预算",allow_unknown=allowed)
    raw=CoverageAssessment(items=[{"requirement_id":"r1","status":"missing","reason":"not found in checked material",
        "finding_ids":["f1"],"resolution":"not_found","unanswered_parts":["average tokens not verified"]}])
    result=normalize_coverage([req],raw,[finding()],checked_requirement_ids={"r1"} if checked else set())
    assert result.items[0].status==expected
    if expected=="covered":
        assert result.items[0].resolution=="not_found"
        assert result.items[0].limitations==["average tokens not verified"]


def test_supporting_gap_does_not_block_user_requirement_but_required_gap_does():
    reqs=[ResearchRequirement(id="r1",description="User fact"),
          ResearchRequirement(id="r2",description="Extra background",required=False)]
    coverage=CoverageAssessment(items=[{"requirement_id":"r1","status":"covered","reason":"supported","finding_ids":["f1"]},
        {"requirement_id":"r2","status":"missing","reason":"optional"}])
    state={"requirements":reqs,"coverage":coverage,"findings":[finding()],"evidence_contract_version":3}
    assert coverage_complete(state)
    reqs[1]=reqs[1].model_copy(update={"required":True})
    assert not coverage_complete(state)


def test_sealing_cannot_downgrade_explicit_user_quote_or_invent_unknown_permission():
    reqs,_=seal_requirements("至少3项原始研究；预算必须核实",[
        ResearchRequirement(id="r1",description="至少3项原始研究",required=False,user_quote="至少3项原始研究"),
        ResearchRequirement(id="r2",description="计算预算",allow_unknown=True)])
    assert reqs[0].required
    assert not reqs[1].allow_unknown
    reqs,_=seal_requirements("比较模型预算；缺少数据明确标注",[ResearchRequirement(id="r1",description="模型和计算预算")])
    assert reqs[0].allow_unknown


def test_verification_uses_same_required_only_gate():
    from datetime import datetime,UTC
    from deeptrace.domain import Evidence, EvidenceLifecycleStatus
    from deeptrace.research.verification import project_verification_result
    source=Evidence(id="paper",canonical_url="https://example.com/paper",title="Paper",media_type="text/plain",
        content_hash="sha256:a",fetched_at=datetime(2026,11,17,tzinfo=UTC),source_quality=0.9,
        status=EvidenceLifecycleStatus.ACTIVE,version=1)
    requirements=[ResearchRequirement(id="r1",description="Required"),ResearchRequirement(id="r2",description="Background",required=False)]
    coverage=CoverageAssessment(items=[{"requirement_id":"r1","status":"covered","reason":"evidence","finding_ids":["f1"]},
        {"requirement_id":"r2","status":"missing","reason":"background not researched"}])
    result=project_verification_result(evidence=[source],bodies={"paper":"A measured experiment."},findings=[finding()],
        source_eligibility={"paper":"eligible"},requirements=requirements,coverage=coverage)
    assert result.coverage_complete


def test_serialized_checked_scope_is_understood_by_response_coverage_gate():
    req=ResearchRequirement(id="r1",description="预算",allow_unknown=True)
    state={"evidence_contract_version":3,"requirements":[req.model_dump()],"findings":[finding().model_dump()],
        "coverage":{"items":[{"requirement_id":"r1","status":"covered","resolution":"not_found",
            "reason":"checked scope","finding_ids":["f1"],"limitations":["not verified here"]}]},
        "field_checks":[{"evidence_id":"paper","version":1,"content_hash":"sha256:a",
            "status":"read_unresolved","ranges":[[0,22]],"target_requirement_ids":["r1"]}]}
    assert coverage_complete(state)
