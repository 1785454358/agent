"""Bounded source supports and coverage survive the real checkpoint boundary."""

import pytest
from pydantic import ValidationError

from deeptrace.domain.evidence import Finding
from deeptrace.domain.execution import ResearchMode, ResearchOutcome
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer


def _support(**changes):
    from deeptrace.domain import evidence

    assert hasattr(evidence, "EvidenceSupport"), "source supports are not implemented"
    return evidence.EvidenceSupport.model_validate(
        {
            "evidence_id": "e-1",
            "version": 2,
            "content_hash": "hash",
            "start": 3,
            "end": 6,
            "quote": "中文🙂",
            **changes,
        }
    )


def _coverage_types():
    from deeptrace.domain import research

    assert hasattr(research, "ResearchRequirement"), "coverage contract is missing"
    return (
        research.ResearchRequirement,
        research.RequirementCoverage,
        research.CoverageAssessment,
    )


def test_support_uses_character_offsets_and_preserves_quote():
    support = _support()
    assert (support.start, support.end, support.quote) == (3, 6, "中文🙂")


@pytest.mark.parametrize(
    "changes",
    [
        {"start": -1},
        {"end": 3},
        {"end": 7},
        {"start": True},
        {"quote": "x" * 501},
        {"version": 0},
        {"tenant_id": "other"},
    ],
)
def test_invalid_support_is_rejected(changes):
    with pytest.raises(ValidationError):
        _support(**changes)


def test_finding_rejects_support_for_an_unlisted_source():
    with pytest.raises(ValidationError, match="support_evidence_not_listed"):
        Finding(
            id="f1",
            claim="fact",
            evidence_ids=["e-other"],
            confidence=0.9,
            supports=[_support()],
        )


def test_finding_cannot_carry_more_than_three_supports():
    with pytest.raises(ValidationError):
        Finding(
            id="f1",
            claim="fact",
            evidence_ids=["e-1"],
            confidence=0.9,
            supports=[_support()] * 4,
        )


def test_legacy_finding_loads_with_empty_support_not_verified_support():
    finding = Finding(id="f1", claim="old", evidence_ids=["e-1"], confidence=1)
    assert "supports" in type(finding).model_fields
    assert finding.supports == []


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "r7"},
        {"id": "r0"},
        {"description": "x" * 501},
        {"description": ""},
        {"gold_answer": "secret"},
    ],
)
def test_requirement_rejects_unknown_ids_unbounded_text_and_oracle_fields(changes):
    requirement, _, _ = _coverage_types()
    with pytest.raises(ValidationError):
        requirement.model_validate({"id": "r1", "description": "Store", **changes})


def test_coverage_rejects_duplicate_requirements_and_finding_ids():
    _, item, assessment = _coverage_types()
    missing = item(requirement_id="r1", status="missing", reason="not read")
    with pytest.raises(ValidationError, match="duplicate_requirement_coverage"):
        assessment(items=[missing, missing])
    with pytest.raises(ValidationError, match="finding_ids must be unique"):
        item(
            requirement_id="r1",
            status="covered",
            reason="read",
            finding_ids=["f1", "f1"],
        )


def test_checkpoint_roundtrip_preserves_requirements_coverage_and_source_offsets():
    requirement, item, assessment = _coverage_types()
    finding = Finding(
        id="f1",
        claim="fact",
        evidence_ids=["e-1"],
        confidence=0.9,
        supports=[_support()],
    )
    outcome = ResearchOutcome(
        mode=ResearchMode.PLAN_EXECUTE,
        evidence_ids=["e-1"],
        findings=[finding],
        executed_steps=3,
        termination_reason="completed",
        evidence_contract_version=2,
        requirements=[requirement(id="r1", description="Store")],
        coverage=assessment(
            items=[
                item(
                    requirement_id="r1",
                    status="covered",
                    reason="read",
                    finding_ids=["f1"],
                )
            ]
        ),
    )
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(outcome))
    assert isinstance(restored, ResearchOutcome)
    assert restored.evidence_contract_version == 2
    assert restored.requirements[0].description == "Store"
    assert restored.coverage.items[0].finding_ids == ["f1"]
    assert restored.findings[0].supports[0].quote == "中文🙂"
    assert restored.findings[0].supports[0].start == 3


def test_legacy_outcome_decodes_without_inventing_requirements():
    outcome = ResearchOutcome(
        mode=ResearchMode.WORKFLOW,
        evidence_ids=[],
        executed_steps=0,
        termination_reason="no_sources",
    )
    assert "evidence_contract_version" in type(outcome).model_fields
    assert outcome.evidence_contract_version == 1
    assert outcome.requirements == []
    assert outcome.coverage is None
