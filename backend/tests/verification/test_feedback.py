from datetime import UTC, datetime

from deeptrace.models import Claim, VerificationIssue, VerificationResult
from deeptrace.verification import build_verification_gaps


def _claim(identity: str, *, key: bool = True) -> Claim:
    return Claim(
        claim_id=identity,
        task_id="task-01",
        section_id="section-01",
        text=f"主张 {identity}",
        kind="factual",
        importance="key" if key else "supporting",
        evidence_ids=["ev-01"],
    )


def _result(
    identity: str,
    verdict: str,
    *,
    blocking: bool = False,
) -> VerificationResult:
    issues = []
    if blocking:
        issues.append(
            VerificationIssue(
                code="source_independence_insufficient",
                severity="blocking",
                message="缺少独立来源",
            )
        )
    return VerificationResult(
        claim_id=identity,
        verdict=verdict,
        reason="核验结果",
        issues=issues,
        verified_at=datetime.now(UTC),
    )


def test_only_key_actionable_claims_create_bounded_gaps() -> None:
    claims = [
        _claim("claim-conflict"),
        _claim("claim-blocking"),
        _claim("claim-unsupported"),
        _claim("claim-supporting", key=False),
        _claim("claim-verified"),
    ]
    results = {
        "claim-conflict": _result("claim-conflict", "conflicted"),
        "claim-blocking": _result(
            "claim-blocking", "partially_supported", blocking=True
        ),
        "claim-unsupported": _result(
            "claim-unsupported", "unsupported"
        ),
        "claim-supporting": _result(
            "claim-supporting", "unsupported"
        ),
        "claim-verified": _result("claim-verified", "verified"),
    }

    gaps = build_verification_gaps(claims, results, max_gaps=2)

    assert len(gaps) == 2
    assert all(gap.priority == "high" for gap in gaps)
    assert all(gap.claim_id != "claim-supporting" for gap in gaps)
    assert all("quote-" not in gap.suggested_query for gap in gaps)
    assert gaps[0].gap_id == build_verification_gaps(
        claims, results, max_gaps=2
    )[0].gap_id

