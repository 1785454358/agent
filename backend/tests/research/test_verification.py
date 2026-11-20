"""Claims only become accepted after host provenance and coverage checks."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deeptrace.domain import (
    CoverageAssessment,
    Evidence,
    EvidenceLifecycleStatus,
    EvidenceSupport,
    Finding,
    ResearchRequirement,
)
from deeptrace.research import (
    Claim,
    ClaimStatus,
    EvidenceGraph,
    EvidenceSpan,
    VerificationAction,
    build_evidence_graph,
    project_verification_result,
    verify_evidence_graph,
)


QUOTE = "The exact sentence that supports this claim."
BODY = f"Header. {QUOTE} More original context."
REQUIREMENTS = (ResearchRequirement(id="r1", description="Verify the documented fact"),)


def _evidence(**changes) -> Evidence:
    values = {
        "id": "evidence-1",
        "canonical_url": "https://example.com/doc",
        "title": "Official original",
        "media_type": "text/html",
        "content_hash": "hash-1",
        "fetched_at": datetime(2026, 11, 13, tzinfo=UTC),
        "source_quality": 0.95,
        "status": EvidenceLifecycleStatus.ACTIVE,
        "version": 1,
    }
    values.update(changes)
    return Evidence(**values)


def _finding(**changes) -> Finding:
    values = {
        "id": "finding-1",
        "claim": "A documented behavior",
        "evidence_ids": ["evidence-1"],
        "confidence": 0.9,
        "supports": [
            EvidenceSupport(
                evidence_id="evidence-1",
                version=1,
                content_hash="hash-1",
                start=BODY.index(QUOTE),
                end=BODY.index(QUOTE) + len(QUOTE),
                quote=QUOTE,
            )
        ],
    }
    values.update(changes)
    return Finding(**values)


def _coverage(status: str = "covered") -> CoverageAssessment:
    return CoverageAssessment(
        items=[
            {
                "requirement_id": "r1",
                "status": status,
                "reason": "Submitted protocol verdict",
                "finding_ids": ["finding-1"],
            }
        ]
    )


def _project(**overrides):
    kwargs = {
        "evidence": [_evidence()],
        "bodies": {"evidence-1": BODY},
        "findings": [_finding()],
        "source_eligibility": {"evidence-1": "eligible"},
        "requirements": REQUIREMENTS,
        "coverage": _coverage(),
    }
    kwargs.update(overrides)
    return project_verification_result(**kwargs)


def test_host_verified_support_produces_accepted_claim_and_synthesis() -> None:
    result = _project()
    claim = result.accepted_claims[0]
    assert claim.status is ClaimStatus.ACCEPTED
    assert claim.requirement_ids == ("r1",)
    assert result.coverage.items[0].status == "covered"
    assert result.coverage_complete
    assert result.recommended_action is VerificationAction.SYNTHESIZE
    restored = type(result).model_validate(result.model_dump(mode="json"))
    assert restored.graph.spans[0].quote == QUOTE


def test_verification_result_survives_the_checkpoint_serializer() -> None:
    from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer

    result = _project()
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(result))
    assert isinstance(restored, type(result))
    assert restored.accepted_claims[0].status is ClaimStatus.ACCEPTED
    assert restored.coverage.items[0].finding_ids == ["finding-1"]


@pytest.mark.parametrize(
    "overrides,expected_issue",
    [
        ({"bodies": {}}, "body_unavailable"),
        ({"bodies": {"evidence-1": "Different original text"}}, "quote_mismatch"),
        ({"source_eligibility": None}, "source_eligibility_unavailable"),
        ({"source_eligibility": {"evidence-1": "uncertain"}}, "source_ineligible_or_uncertain"),
        ({"evidence": [_evidence(version=2)]}, "evidence_version_mismatch"),
        ({"evidence": [_evidence(status=EvidenceLifecycleStatus.SUPERSEDED)]}, "evidence_not_active"),
    ],
)
def test_invalid_provenance_cannot_cover_a_requirement(overrides, expected_issue) -> None:
    result = _project(**overrides, can_replan=False)
    assert result.accepted_claims == ()
    assert result.coverage.items[0].status == "missing"
    assert result.coverage.items[0].reason == "unsupported_requirement_coverage"
    assert expected_issue in result.issues[0]
    assert result.recommended_action is VerificationAction.PARTIAL


def test_every_support_must_be_valid_not_just_one() -> None:
    second = _evidence(id="evidence-2", canonical_url="https://example.com/other")
    finding = _finding(
        evidence_ids=["evidence-1", "evidence-2"],
        supports=[
            *_finding().supports,
            EvidenceSupport(
                evidence_id="evidence-2",
                version=1,
                content_hash="hash-1",
                start=0,
                end=4,
                quote="Blog",
            ),
        ],
    )
    result = _project(
        evidence=[_evidence(), second],
        bodies={"evidence-1": BODY, "evidence-2": "Blog content"},
        findings=[finding],
        source_eligibility={"evidence-1": "eligible", "evidence-2": "ineligible"},
    )
    assert result.accepted_claims == ()
    assert result.coverage.items[0].status == "missing"


def test_accepted_claim_does_not_upgrade_a_missing_model_verdict() -> None:
    result = _project(coverage=_coverage("missing"))
    assert len(result.accepted_claims) == 1
    assert result.coverage.items[0].status == "missing"
    assert result.recommended_action is VerificationAction.REPLAN


def test_conflicting_verdict_is_preserved_with_bounded_support_links() -> None:
    result = _project(coverage=_coverage("conflicting"))
    assert result.coverage.items[0].status == "conflicting"
    assert result.coverage.items[0].finding_ids == ["finding-1"]
    assert not result.coverage_complete


def test_no_requirements_or_unknown_coverage_is_not_complete() -> None:
    result = _project(requirements=(), coverage=None)
    assert result.coverage is None
    assert result.recommended_action is VerificationAction.PARTIAL
    with pytest.raises(ValueError, match="unknown requirement"):
        verify_evidence_graph(
            result.graph,
            REQUIREMENTS,
            submitted_coverage=CoverageAssessment(
                items=[{"requirement_id": "r2", "status": "missing", "reason": "unknown"}]
            ),
        )


def test_graph_rejects_duplicate_claim_ids_and_dangling_spans() -> None:
    with pytest.raises(ValidationError):
        _project(findings=[_finding(), _finding()])
    with pytest.raises(ValidationError, match="unavailable evidence span"):
        EvidenceGraph.model_validate(
            {"claims": [{
                "id": "claim-1", "text": "fact", "confidence": 0.9,
                "support_span_ids": ["missing-span"],
            }]}
        )
    with pytest.raises(ValidationError, match="clean_supports"):
        EvidenceGraph.model_validate(
            {"claims": [{
                "id": "claim-1", "text": "unsupported", "confidence": 0.9,
                "status": "accepted",
            }]}
        )


def test_graph_rejects_accepted_claim_on_superseded_evidence_and_prefers_active_source() -> None:
    support = _finding().supports[0]
    span = EvidenceSpan.from_support(support)
    superseded = _evidence(status=EvidenceLifecycleStatus.SUPERSEDED)
    with pytest.raises(ValidationError, match="requires_active_evidence"):
        EvidenceGraph(
            sources=(),
            evidence=(superseded,),
            spans=(span,),
            claims=(
                Claim(
                    id="claim-1",
                    text="fact",
                    confidence=0.9,
                    support_span_ids=(span.id,),
                    status=ClaimStatus.ACCEPTED,
                ),
            ),
        )

    active = _evidence(
        id="evidence-2", version=2, content_hash="hash-2", title="Current original"
    )
    graph = build_evidence_graph(
        evidence=[superseded, active],
        bodies={},
        findings=[],
        source_eligibility=None,
    )
    assert len(graph.sources) == 1
    assert graph.sources[0].title == "Current original"
