"""把关键 Claim 的可行动缺口转换为有界补搜请求。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from deeptrace.evidence import stable_id
from deeptrace.models import Claim, VerificationGap, VerificationResult


_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_verification_gaps(
    claims: Sequence[Claim],
    results: Mapping[str, VerificationResult],
    max_gaps: int,
) -> list[VerificationGap]:
    """只为关键且可通过补搜改善的结果生成稳定 Gap。"""
    gaps: list[VerificationGap] = []
    for claim in claims:
        if claim.importance != "key":
            continue
        result = results.get(claim.claim_id)
        if result is None or result.verdict in {"verified", "out_of_range"}:
            continue
        blocking = [
            issue for issue in result.issues if issue.severity == "blocking"
        ]
        if (
            result.verdict not in {"conflicted", "unsupported"}
            and not blocking
        ):
            continue

        if blocking:
            reason_code = blocking[0].code
            description = blocking[0].message
        else:
            reason_code = result.verdict
            description = result.reason
        priority = (
            "high"
            if result.verdict in {"conflicted", "unsupported"} or blocking
            else "medium"
        )
        query = f"{claim.text}；补充要求：{description}"
        gaps.append(
            VerificationGap(
                gap_id=stable_id(
                    "gap", claim.task_id, claim.claim_id, reason_code
                ),
                task_id=claim.task_id,
                section_id=claim.section_id,
                claim_id=claim.claim_id,
                reason_code=reason_code,
                description=description,
                suggested_query=query,
                preferred_source_kinds=[
                    "official",
                    "academic",
                    "reputable_secondary",
                ],
                priority=priority,
            )
        )

    gaps.sort(
        key=lambda item: (
            _PRIORITY_ORDER[item.priority],
            item.claim_id or "",
            item.gap_id,
        )
    )
    return gaps[: max(0, max_gaps)]

