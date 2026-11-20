"""Strategy finalization follows the host verification verdict, not legacy flags."""

from deeptrace.domain import CoverageAssessment, ResearchRequirement
from deeptrace.research import (
    EvidenceGraph,
    VerificationAction,
    VerificationResult,
)
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation
from deeptrace.strategies.workflow.nodes import finalize_node


def _coverage(status: str) -> CoverageAssessment:
    return CoverageAssessment(
        items=[
            {
                "requirement_id": "r1",
                "status": status,
                "reason": "test verdict",
            }
        ]
    )


def _verification(status: str) -> VerificationResult:
    return VerificationResult(
        graph=EvidenceGraph(),
        coverage=_coverage(status),
        recommended_action=(
            VerificationAction.SYNTHESIZE
            if status == "covered"
            else VerificationAction.REPLAN
        ),
        reason="host verification",
    )


def _state(*, verification_status: str, evaluation_sufficient: bool | None):
    evaluation = (
        ReferenceWorkflowEvaluation(
            findings=[],
            coverage=_coverage("covered"),
            source_checks=[],
            unresolved_gaps=[],
            sufficient=True,
        )
        if evaluation_sufficient else None
    )
    return {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": "Answer",
        "current_date": "2026-11-13",
        "timezone": "Asia/Shanghai",
        "requirements": [ResearchRequirement(id="r1", description="Fact")],
        "evidence_contract_version": 3,
        "evidence_ids": ["evidence-1"],
        "findings": [],
        "source_eligibility": {"evidence-1": "eligible"},
        "topic_outcomes": [],
        "executed_steps": 1,
        "coverage": _coverage("covered"),
        "evaluation": evaluation,
        "verification": _verification(verification_status),
    }


def test_missing_host_coverage_cannot_finish_even_when_legacy_evaluation_says_complete() -> None:
    update = finalize_node(
        _state(verification_status="missing", evaluation_sufficient=True)
    )
    assert update["outcome"].termination_reason == "insufficient_evidence"


def test_host_coverage_can_finish_without_legacy_evaluation() -> None:
    update = finalize_node(
        _state(verification_status="covered", evaluation_sufficient=None)
    )
    assert update["outcome"].termination_reason == "completed"
