"""Characterization tests for the legacy turn-finalization contract."""

from deeptrace.domain import (
    CoverageAssessment,
    CitationRef,
    EvidenceSupport,
    ExecutionStatus,
    Finding,
    ResearchMode,
    ResearchOutcome,
    ResponseMode,
    ResponseOutcome,
)
from deeptrace.domain.coverage import ResearchRequirement
from deeptrace.harness.graph import _finalize_turn
from deeptrace.research import (
    EvidenceGraph,
    VerificationAction,
    VerificationResult,
)


def _finding() -> Finding:
    quote = "Only this original sentence supports the requirement."
    return Finding(
        id="finding-1",
        claim=quote,
        evidence_ids=["evidence-1"],
        confidence=0.9,
        supports=[
            EvidenceSupport(
                evidence_id="evidence-1",
                version=1,
                content_hash="hash-1",
                start=0,
                end=len(quote),
                quote=quote,
            )
        ],
    )


def _research(*, complete: bool) -> ResearchOutcome:
    finding = _finding()
    status = "covered" if complete else "missing"
    return ResearchOutcome(
        mode=ResearchMode.WORKFLOW,
        evidence_contract_version=3,
        requirements=[ResearchRequirement(id="r1", description="One verifiable fact")],
        coverage=CoverageAssessment(
            items=[
                {
                    "requirement_id": "r1",
                    "status": status,
                    "reason": "baseline",
                    "finding_ids": [finding.id] if complete else [],
                }
            ]
        ),
        findings=[finding] if complete else [],
        evidence_ids=["evidence-1"],
        unresolved_gaps=[] if complete else ["r1:missing:baseline"],
        executed_steps=1,
        termination_reason="completed" if complete else "insufficient_evidence",
    )


def _response(*, partial: bool) -> ResponseOutcome:
    if partial:
        return ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="Partial grounded content.",
            partial_reason="insufficient_evidence",
        )
    return ResponseOutcome(
        response_mode=ResponseMode.ANSWER,
        content="Complete grounded content [1].",
        citations=[CitationRef(evidence_id="evidence-1", marker="[1]")],
        cited_evidence_ids=["evidence-1"],
    )


def test_completed_research_and_complete_response_finish_the_turn() -> None:
    update = _finalize_turn(
        {
            "turn": {
                "run_id": "run-1",
                "requires_research": True,
                "research_outcome": _research(complete=True),
                "response_outcome": _response(partial=False),
            }
        }
    )
    assert update["turn"]["status"] is ExecutionStatus.COMPLETED


def _verification(status: str) -> VerificationResult:
    return VerificationResult(
        graph=EvidenceGraph(),
        coverage=CoverageAssessment(
            items=[
                {
                    "requirement_id": "r1",
                    "status": status,
                    "reason": "host verdict",
                }
            ]
        ),
        recommended_action=(
            VerificationAction.SYNTHESIZE
            if status == "covered"
            else VerificationAction.REPLAN
        ),
        reason="host verification",
    )


def test_host_verification_overrides_legacy_complete_coverage() -> None:
    update = _finalize_turn(
        {
            "turn": {
                "run_id": "run-1",
                "requires_research": True,
                "research_outcome": _research(complete=True),
                "verification": _verification("missing"),
                "response_outcome": _response(partial=False),
            }
        }
    )
    assert update["turn"]["status"] is ExecutionStatus.PARTIAL


def test_finished_workflow_preserves_grounded_partial_answer_as_completed_run() -> None:
    # Current product semantics: a fixed workflow may finish with evidence gaps
    # when the response policy has already produced a bounded partial answer.
    update = _finalize_turn(
        {
            "turn": {
                "run_id": "run-1",
                "requires_research": True,
                "research_outcome": _research(complete=False),
                "response_outcome": _response(partial=True),
            }
        }
    )
    assert update["turn"]["status"] is ExecutionStatus.COMPLETED
