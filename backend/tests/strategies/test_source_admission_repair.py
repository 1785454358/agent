"""A self-contradictory source assessment can be repaired, never admitted as-is."""

import json

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import ResearchRequirement, ResearchTopicOutcome
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation
from deeptrace.tools.evidence_store import EvidenceDraft
from strategies.fixtures import FIXED_NOW, build_gateway_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize("repairs,repair_limit,expected_calls,covered", [
    (True, 1, 2, True), (False, 1, 2, False), (True, 0, 1, False),
])
async def test_repair_rechecks_coverage_after_removing_ineligible_source_support(
    repairs, repair_limit, expected_calls, covered,
):
    calls = []
    class Model:
        async def invoke(self, *, role, messages, **kwargs):
            prompt = str(messages[-1].content)
            calls.append(prompt)
            view = json.loads(prompt.split("EVIDENCE_VIEW_JSON:\n", 1)[1])
            refs = [p["ref"] for p in view["passages"]]
            supports = refs[:1] if repairs and len(calls) > 1 else refs[:2]
            return AIMessage(content=json.dumps({
                "findings": [{"id": "f1", "claim": "Exact supported fact.", "confidence": 0.9,
                              "supports": [{"ref": ref} for ref in supports]}],
                "coverage": {"items": [{"requirement_id": "r1", "status": "covered",
                                         "reason": "Supported by the actual original", "finding_ids": ["f1"]}]},
                "source_checks": [
                    {"source": "s1", "status": "eligible", "reason": "Official original"},
                    {"source": "s2", "status": "ineligible", "reason": "Third-party blog"},
                ], "unresolved_gaps": [], "sufficient": True,
            }))
    fixture = build_gateway_fixture(model_gateway=Model())
    records, anchors = [], []
    for index, body in enumerate(["Exact supported fact.", "Unverified blog claim."]):
        record = await fixture.evidence_store.ingest("workspace-1", EvidenceDraft(
            canonical_url=f"https://example.com/{index}", title=f"Source {index}",
            body=body, media_type="text/plain", fetched_at=FIXED_NOW, source_quality=0.9,
        ))
        records.append(record)
        anchors.append(ReadEvidenceAnchor(
            evidence_id=record.id, version=record.version, content_hash=record.content_hash,
            start=0, end=len(body),
        ))
    result = await run_evidence_evaluation({
        "run_id": "run-1", "thread_id": "thread-1", "current_date": "2026-10-24",
        "timezone": "Asia/Shanghai", "question": "Use only official originals to explain the fact",
        "evidence_contract_version": 3,
        "requirements": [ResearchRequirement(id="r1", description="Explain the supported fact")],
        "evidence_ids": [r.id for r in records],
        "topic_outcomes": [ResearchTopicOutcome(query="fact", evidence_ids=[r.id for r in records],read_anchors=anchors)],
    }, fixture.context, ReferenceWorkflowEvaluation, repair_attempts=repair_limit)
    assert len(calls) == expected_calls
    assert (result["coverage"].items[0].status == "covered") is covered
    assert result["source_eligibility"][records[1].id] == "ineligible"
    assert result["assessment"].sufficient is covered
    verification = result["verification"]
    assert verification is not None
    assert verification.coverage_complete is covered
    if covered:
        assert all(s.evidence_id == records[0].id for f in result["findings"] for s in f.supports)
        assert "不合格来源" in calls[1]
        assert verification.accepted_claims[0].id == "f1"
    else:
        assert not result["findings"]
        assert verification.accepted_claims == ()


@pytest.mark.asyncio
async def test_failed_repair_cannot_keep_the_rejected_complete_assessment() -> None:
    calls = []

    class Model:
        async def invoke(self, *, role, messages, **kwargs):
            calls.append(str(messages[-1].content))
            if len(calls) > 1:
                return AIMessage(content="not valid json")
            return AIMessage(content=json.dumps({
                "findings": [{
                    "id": "f1",
                    "claim": "Supported only by an ineligible source.",
                    "confidence": 0.9,
                    "supports": [{"ref": "p1"}],
                }],
                "coverage": {"items": [{
                    "requirement_id": "r1",
                    "status": "covered",
                    "reason": "Rejected on repair",
                    "finding_ids": ["f1"],
                }]},
                "source_checks": [
                    {"source": "s1", "status": "ineligible", "reason": "blog"},
                ],
                "unresolved_gaps": [],
                "sufficient": True,
            }))

    fixture = build_gateway_fixture(model_gateway=Model())
    body = "Unverified blog claim."
    record = await fixture.evidence_store.ingest("workspace-1", EvidenceDraft(
        canonical_url="https://example.com/blog",
        title="Blog",
        body=body,
        media_type="text/plain",
        fetched_at=FIXED_NOW,
        source_quality=0.2,
    ))
    result = await run_evidence_evaluation({
        "run_id": "run-1",
        "thread_id": "thread-1",
        "current_date": "2026-10-24",
        "timezone": "Asia/Shanghai",
        "question": "Use an official original",
        "evidence_contract_version": 3,
        "requirements": [ResearchRequirement(id="r1", description="Official fact")],
        "evidence_ids": [record.id],
        "topic_outcomes": [ResearchTopicOutcome(
            query="fact",
            evidence_ids=[record.id],
            read_anchors=[ReadEvidenceAnchor(
                evidence_id=record.id,
                version=record.version,
                content_hash=record.content_hash,
                start=0,
                end=len(body),
            )],
        )],
    }, fixture.context, ReferenceWorkflowEvaluation, repair_attempts=1)

    assert len(calls) == 2
    assert result["assessment"] is None
    assert result["coverage"].items[0].status == "missing"
    assert "evaluation_unavailable" in result["diagnostic_gaps"]
    assert result["verification"] is not None
    assert result["verification"].accepted_claims == ()


@pytest.mark.asyncio
async def test_unused_rejected_finding_does_not_repeat_an_entire_valid_assessment() -> None:
    calls = []

    class Model:
        async def invoke(self, *, role, messages, **kwargs):
            calls.append(str(messages[-1].content))
            if len(calls) > 1:
                return AIMessage(content="not valid json")
            return AIMessage(content=json.dumps({
                "findings": [
                    {"id": "f1", "claim": "Official fact.", "confidence": 0.9,
                     "supports": [{"ref": "p1"}]},
                    {"id": "f2", "claim": "Blog claim.", "confidence": 0.9,
                     "supports": [{"ref": "p2"}]},
                ],
                "coverage": {"items": [{
                    "requirement_id": "r1",
                    "status": "covered",
                    "reason": "official source",
                    "finding_ids": ["f1"],
                }]},
                "source_checks": [
                    {"source": "s1", "status": "eligible", "reason": "official"},
                    {"source": "s2", "status": "ineligible", "reason": "blog"},
                ],
                "unresolved_gaps": [],
                "sufficient": True,
            }))

    fixture = build_gateway_fixture(model_gateway=Model())
    records = []
    for index, body in enumerate(("Official fact.", "Blog claim.")):
        record = await fixture.evidence_store.ingest("workspace-1", EvidenceDraft(
            canonical_url=f"https://example.com/{index}",
            title=f"Source {index}",
            body=body,
            media_type="text/plain",
            fetched_at=FIXED_NOW,
            source_quality=0.9 if index == 0 else 0.2,
        ))
        records.append(record)

    result = await run_evidence_evaluation({
        "run_id": "run-1", "thread_id": "thread-1", "current_date": "2026-10-24",
        "timezone": "Asia/Shanghai", "question": "Use the official original",
        "evidence_contract_version": 3,
        "requirements": [ResearchRequirement(id="r1", description="Official fact")],
        "evidence_ids": [r.id for r in records],
        "topic_outcomes": [ResearchTopicOutcome(
            query="fact",
            evidence_ids=[r.id for r in records],
            read_anchors=[
                ReadEvidenceAnchor(
                    evidence_id=record.id,
                    version=record.version,
                    content_hash=record.content_hash,
                    start=0,
                    end=len(body),
                )
                for record, body in zip(records, ("Official fact.", "Blog claim."))
            ],
        )],
    }, fixture.context, ReferenceWorkflowEvaluation, repair_attempts=1)

    assert len(calls) == 1
    assert result["assessment"] is not None
    assert result["coverage"].items[0].status == "covered"
    assert [f.id for f in result["findings"]] == ["f1"]
    assert "source_admission_repair" not in result["diagnostic_gaps"]
    assert result["verification"].coverage_complete
    assert result["verification"].accepted_claims[0].id == "f1"
