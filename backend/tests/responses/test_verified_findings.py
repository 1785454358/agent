"""The writer receives only claims accepted by the host verification plane."""

from datetime import UTC, datetime

import pytest

from deeptrace.domain import (
    CoverageAssessment,
    EvidenceSupport,
    Finding,
    ResearchMode,
    ResearchOutcome,
    ResearchRequirement,
    ResponseInput,
    ResponseMode,
)
from deeptrace.responses.evidence import assemble_response_materials
from deeptrace.tools.evidence_store import EvidenceDraft
from strategies.fixtures import TENANT_ID, build_gateway_fixture


NOW = datetime(2026, 11, 13, tzinfo=UTC)


async def _materials(verified_finding_ids):
    fixture = build_gateway_fixture()
    records = []
    findings = []
    for index, quote in enumerate(("First supported fact.", "Second supported fact.")):
        record = await fixture.evidence_store.ingest(
            TENANT_ID,
            EvidenceDraft(
                canonical_url=f"https://example.com/{index}",
                title=f"Source {index}",
                body=quote,
                media_type="text/plain",
                fetched_at=NOW,
                source_quality=0.9,
            ),
        )
        records.append(record)
        findings.append(
            Finding(
                id=f"f{index + 1}",
                claim=quote,
                evidence_ids=[record.id],
                confidence=0.9,
                supports=[
                    EvidenceSupport(
                        evidence_id=record.id,
                        version=record.version,
                        content_hash=record.content_hash,
                        start=0,
                        end=len(quote),
                        quote=quote,
                    )
                ],
            )
        )
    research = ResearchOutcome(
        mode=ResearchMode.WORKFLOW,
        evidence_contract_version=3,
        requirements=[ResearchRequirement(id="r1", description="Both facts")],
        coverage=CoverageAssessment(
            items=[
                {
                    "requirement_id": "r1",
                    "status": "covered",
                    "reason": "two verified facts",
                    "finding_ids": ["f1", "f2"],
                }
            ]
        ),
        findings=findings,
        evidence_ids=[record.id for record in records],
        source_eligibility={record.id: "eligible" for record in records},
        executed_steps=1,
        termination_reason="completed",
    )
    response_input = ResponseInput(
        question="Provide both facts",
        response_mode=ResponseMode.ANSWER,
        research_outcome=research,
        active_evidence_ids=[record.id for record in records],
        verified_finding_ids=verified_finding_ids,
    )
    return await assemble_response_materials(
        fixture.context, response_input, records, per_source_chars=2000
    )


@pytest.mark.asyncio
async def test_verified_ids_filter_claims_without_discarding_eligible_originals() -> None:
    materials = await _materials(["f1"])
    assert [finding.id for finding in materials.findings] == ["f1"]
    assert len(materials.sources) == 2
    assert "https://example.com/0" in materials.sources[0]
    assert "https://example.com/1" in materials.sources[1]


@pytest.mark.asyncio
async def test_empty_verified_set_publishes_no_claims() -> None:
    materials = await _materials([])
    assert materials.findings == []
    assert len(materials.sources) == 2
    assert all(materials.passages_by_source.values())


@pytest.mark.asyncio
async def test_legacy_none_keeps_previous_behavior() -> None:
    materials = await _materials(None)
    assert {finding.id for finding in materials.findings} == {"f1", "f2"}
