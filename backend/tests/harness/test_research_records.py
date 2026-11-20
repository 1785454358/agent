import pytest

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.research_findings import RecordFindingsArguments, resolve_recorded_findings
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


async def branch_submission():
    fixture = build_gateway_fixture()
    body = "Model-A achieves 71.2 on Benchmark-B.\nMaximum length: 4096 tokens."
    record = await seed(fixture, 1, body)
    cut = body.index("Maximum")
    references = {name: ReadEvidenceAnchor(evidence_id=record.id, version=record.version,
        content_hash=record.content_hash, start=a, end=b)
        for name, a, b in [("n1", 0, cut), ("n2", cut, len(body))]}
    task = ResearchTopicInput(run_id="run-1", thread_id="thread-1", caller_id="worker-1",
        query="Experimental setup", mode=ResearchMode.MULTI_AGENT, authorized_evidence_ids=[record.id])
    arguments = RecordFindingsArguments.model_validate({"findings": [{"claim": "A bounded experiment",
        "refs": ["n1"], "confidence": 0.9, "experiments": [{
            "model": {"value": "Model-A", "refs": ["n1"]},
            "budget": {"value": "4096 tokens", "refs": ["n2"]}}]}]})
    findings = await resolve_recorded_findings(arguments, task=task, references=references,
        existing=[], context=fixture.context)
    return fixture, record, body, findings


@pytest.mark.asyncio
async def test_branch_submission_keeps_protocol_fields_outside_claim_quote():
    _, _, _, findings = await branch_submission()
    assert findings[0].experiments[0].budget.value == "4096 tokens"
    index = findings[0].experiments[0].budget.support_indices[0]
    assert findings[0].supports[index].quote == "Maximum length: 4096 tokens."


@pytest.mark.asyncio
async def test_branch_records_reach_evaluator_with_current_passage_references():
    import json
    from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
    fixture, record, body, findings = await branch_submission()
    view = await assemble_reference_evaluation_view(fixture.context, question="experimental setup budget",
        requirements=[], evidence_ids=[record.id], findings=[], research_findings=findings,
        read_anchors=[ReadEvidenceAnchor(evidence_id=record.id, version=record.version,
            content_hash=record.content_hash, start=0, end=len(body))])
    data = json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:\n")[1])
    cell = data["research_findings"][0]["experiments"][0]["budget"]
    assert cell["value"] == "4096 tokens"
    assert "4096 tokens" in view.references[cell["refs"][0]].text
