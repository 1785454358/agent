"""A multi-part review must keep enough original text for each requirement."""

import pytest

from deeptrace.domain import ResearchRequirement
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
async def test_supplement_window_keeps_prior_support_and_new_reads_without_granting_admission():
    import json

    from deeptrace.domain import EvidenceSupport, Finding, ResearchTopicOutcome
    from deeptrace.strategies.evidence_evaluation import run_evidence_evaluation
    from deeptrace.strategies.plan_execute.models import ReferenceExecutorDecision
    from strategies.fixtures import ScriptedModelGateway

    def evaluate(prompt):
        assert "Previously verified context detail." in prompt
        assert "New task behavior 0." in prompt
        return json.dumps(
            {
                "action": "replan",
                "reason": "Admission still requires checks",
                "coverage": {
                    "items": [
                        {
                            "requirement_id": f"r{i}",
                            "status": "missing",
                            "reason": "Unchecked",
                        }
                        for i in (1, 2)
                    ]
                },
            }
        )

    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway({"evaluator": evaluate})
    )
    old = await seed(fixture, 0, "Previously verified context detail.")
    new = [await seed(fixture, i + 1, f"New task behavior {i}.") for i in range(8)]
    old_support = EvidenceSupport(
        evidence_id=old.id,
        version=old.version,
        content_hash=old.content_hash,
        start=0,
        end=35,
        quote="Previously verified context detail.",
    )
    result = await run_evidence_evaluation(
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "current_date": "2026-10-11",
            "timezone": "Asia/Shanghai",
            "question": "Compare context and task behavior",
            "evidence_contract_version": 3,
            "requirements": [
                ResearchRequirement(id=f"r{i}", description=f"Behavior {i}")
                for i in (1, 2)
            ],
            "evidence_ids": [old.id, *(r.id for r in new)],
            "findings": [
                Finding(
                    id="f1",
                    claim="Previous context fact",
                    confidence=0.9,
                    evidence_ids=[old.id],
                    supports=[old_support],
                )
            ],
            "supplement_targets": {"new query": ["r2"]},
            "topic_outcomes": [
                ResearchTopicOutcome(
                    query="new query",
                    evidence_ids=[r.id for r in new],
                    read_anchors=[
                        ReadEvidenceAnchor(
                            evidence_id=r.id,
                            version=r.version,
                            content_hash=r.content_hash,
                            start=0,
                            end=len(f"New task behavior {i}."),
                        )
                        for i, r in enumerate(new)
                    ],
                )
            ],
        },
        fixture.context,
        ReferenceExecutorDecision,
    )
    assert not result["findings"]
    assert all(
        status == "uncertain" for status in result["source_eligibility"].values()
    )


@pytest.mark.asyncio
async def test_five_complete_read_blocks_survive_the_review_material_window():
    fixture = build_gateway_fixture()
    blocks = [
        f"## Doc.api_{i}\n"
        + ("Full conditions apply. " * 31)
        + f" Unique detail {i}.\n\n"
        for i in range(5)
    ]
    body = "".join(blocks)
    record = await seed(fixture, 1, body)
    position, anchors = 0, []
    for block in blocks:
        anchors.append(
            ReadEvidenceAnchor(
                evidence_id=record.id,
                version=record.version,
                content_hash=record.content_hash,
                start=position,
                end=position + len(block),
            )
        )
        position += len(block)
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="Compare APIs",
        requirements=[
            ResearchRequirement(
                id=f"r{i + 1}", description=f"Doc.api_{i} complete behavior"
            )
            for i in range(5)
        ],
        evidence_ids=[record.id],
        findings=[],
        read_anchors=anchors,
    )
    for i in range(5):
        assert f"Unique detail {i}." in view.prompt
