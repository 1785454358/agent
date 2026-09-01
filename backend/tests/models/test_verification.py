from datetime import UTC, datetime

from deeptrace import models


def test_verification_models_preserve_assessments_and_defaults() -> None:
    assert hasattr(models, "VerificationResult")
    assert hasattr(models, "TaskVerificationSummary")

    result = models.VerificationResult(
        claim_id="claim-01",
        verdict="verified",
        reason="原文直接支持",
        supporting_evidence_ids=["evidence-01"],
        refuting_evidence_ids=[],
        source_identities=["example.com"],
        assessments=[
            models.EvidenceAssessment(
                evidence_id="evidence-01",
                relation="supports",
                reason="数值与时间一致",
            )
        ],
        issues=[],
        verified_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    summary = models.TaskVerificationSummary(task_id="task-01")

    assert result.assessments[0].relation == "supports"
    assert models.VerificationResult.model_validate_json(
        result.model_dump_json()
    ) == result
    assert summary.verified_claim_ids == []
    assert summary.supplement_rounds == 0


def test_section_result_accepts_verification_summary(
    section_result,
) -> None:
    assert hasattr(models, "TaskVerificationSummary")
    summary = models.TaskVerificationSummary(
        task_id=section_result.task_id,
        verified_claim_ids=["claim-01"],
    )

    value = section_result.model_copy(
        update={"claim_ids": ["claim-01"], "verification": summary}
    )

    assert value.claim_ids == ["claim-01"]
    assert value.verification == summary
