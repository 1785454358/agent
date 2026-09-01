"""Claim 核验公共接口。"""

from deeptrace.verification.rules import (
    RuleCheckResult,
    check_claim_rules,
    eligible_evidence,
    source_identities,
)
from deeptrace.verification.feedback import build_verification_gaps
from deeptrace.verification.service import (
    VerifierAgent,
    VerifierClaimDraft,
    VerifierDraft,
    merge_verdict,
    parse_verifier_draft,
)

__all__ = [
    "RuleCheckResult",
    "VerifierAgent",
    "VerifierClaimDraft",
    "VerifierDraft",
    "build_verification_gaps",
    "check_claim_rules",
    "eligible_evidence",
    "merge_verdict",
    "parse_verifier_draft",
    "source_identities",
]
