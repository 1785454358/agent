"""Planning a gap must not repeat every expanded original quote per finding."""
import json

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import (
    CoverageAssessment,
    EvidenceSupport,
    Finding,
    ResearchRequirement,
)
from deeptrace.harness.model_context import message_tokens
from deeptrace.strategies.evidence_evaluation import supplement_plan
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
async def test_expanded_citations_do_not_crowd_out_gap_planning_budget():
    captured = []

    class Gateway:
        async def invoke(self, *, messages, **kwargs):
            captured.extend(messages)
            return AIMessage(content=json.dumps({"tasks": [{"query": "missing result",
                "target_requirement_ids": ["r2"]}]}))

    fixture = build_gateway_fixture(model_gateway=Gateway())
    body = "ORIGINAL_QUOTE_MARKER applies only within the experiment. " * 50
    record = await seed(fixture, 1, body)
    supports = [EvidenceSupport(evidence_id=record.id, version=record.version,
        content_hash=record.content_hash, start=start, end=min(start+500, len(body)),
        quote=body[start:start+500]) for start in range(0, len(body), 500)]
    findings = [Finding(id=f"f{i}", claim=f"Accepted result {i}", evidence_ids=[record.id],
        confidence=0.9, supports=supports) for i in range(10)]
    requirements = [ResearchRequirement(id="r1", description="known result"),
        ResearchRequirement(id="r2", description="missing result")]
    result = await supplement_plan({
        "run_id": "run-1", "thread_id": "thread-1", "question": "known and missing results",
        "current_date": "2026-10-11", "timezone": "Asia/Shanghai", "evidence_contract_version": 3,
        "requirements": requirements, "evidence_ids": [record.id], "findings": findings,
        "coverage": CoverageAssessment(items=[
            {"requirement_id": "r1", "status": "covered", "reason": "supported", "finding_ids": ["f0"]},
            {"requirement_id": "r2", "status": "missing", "reason": "no original evidence"},
        ]),
    }, fixture.context, role="replanner", dispatched=["known result"], limit=2)
    assert message_tokens(captured) < 3500
    prompt = captured[-1].content
    assert "Accepted result 9" in prompt and record.canonical_url in prompt
    assert "no original evidence" in prompt
    assert result["supplement_targets"] == {"missing result": ["r2"]}
    assert len(findings[0].supports) > 5
