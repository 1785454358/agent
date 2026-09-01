"""不调用模型的 Claim 证据资格与来源门槛检查。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from deeptrace.models import (
    Claim,
    Evidence,
    ResearchTimeRange,
    Source,
    VerificationIssue,
    VerificationVerdict,
)


QUALIFIED_SOURCE_KINDS = {"official", "academic", "reputable_secondary"}
AUTHORITATIVE_SOURCE_KINDS = {"official", "academic"}


class RuleCheckResult(BaseModel):
    """LLM 语义核验前不可覆盖的本地检查结果。"""

    eligible_evidence_ids: list[str] = Field(default_factory=list)
    source_identities: list[str] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    forced_verdict: VerificationVerdict | None = None

    @property
    def blocking_issues(self) -> list[VerificationIssue]:
        return [item for item in self.issues if item.severity == "blocking"]


def eligible_evidence(
    claim: Claim,
    evidence: Mapping[str, Evidence],
) -> list[Evidence]:
    """按 Claim 引用顺序返回位置和上下文均合格的 Evidence。"""
    result: list[Evidence] = []
    for identity in claim.evidence_ids:
        item = evidence.get(identity)
        if item is None or item.location_status != "exact":
            continue
        if item.task_id != claim.task_id or item.section_id != claim.section_id:
            continue
        if item.temporal_relation == "out_of_range":
            continue
        result.append(item)
    return result


def source_identities(
    items: Sequence[Evidence],
    sources: Mapping[str, Source],
) -> list[str]:
    """将子域名折叠为注册域，并保持首次引用顺序。"""
    # 延迟导入，避免 prompts 加载期间触发整个 orchestration 包。
    from deeptrace.orchestration.quality import source_identity

    identities: list[str] = []
    seen: set[str] = set()
    for item in items:
        source = sources.get(item.source_id)
        if source is None:
            continue
        identity = source_identity(
            source.canonical_url or source.final_url or source.requested_url
        )
        if identity in seen:
            continue
        seen.add(identity)
        identities.append(identity)
    return identities


def _issue(code: str, message: str) -> VerificationIssue:
    return VerificationIssue(
        code=code, severity="blocking", message=message
    )


def check_claim_rules(
    claim: Claim,
    evidence: Mapping[str, Evidence],
    sources: Mapping[str, Source],
    time_range: ResearchTimeRange | None,
) -> RuleCheckResult:
    """执行 Evidence、时间、来源质量与数值完整性门槛。"""
    if claim.event_start and claim.event_end and time_range:
        # 延迟导入，避免 prompts -> verification -> context -> prompts 的加载环。
        from deeptrace.context.temporal import normalize_temporal_relation

        relation = normalize_temporal_relation(
            time_range, None, claim.event_start, claim.event_end
        )
        if relation == "out_of_range":
            return RuleCheckResult(
                forced_verdict="out_of_range",
                issues=[
                    _issue(
                        "claim_out_of_range",
                        "Claim 事件时间超出研究范围",
                    )
                ],
            )

    issues: list[VerificationIssue] = []
    for identity in claim.evidence_ids:
        item = evidence.get(identity)
        if item is None:
            issues.append(_issue("evidence_missing", f"Evidence 不存在：{identity}"))
            continue
        if item.location_status != "exact":
            issues.append(
                _issue("evidence_unlocated", f"Evidence 未精确定位：{identity}")
            )
            continue
        if item.task_id != claim.task_id or item.section_id != claim.section_id:
            issues.append(
                _issue("evidence_context_mismatch", "Evidence 与 Claim 任务不一致")
            )
        if item.temporal_relation == "out_of_range":
            issues.append(
                _issue("evidence_out_of_range", "Evidence 事件时间超出研究范围")
            )

    eligible = eligible_evidence(claim, evidence)
    for item in eligible:
        if item.source_id not in sources:
            issues.append(
                _issue("source_missing", f"Source 不存在：{item.source_id}")
            )
    eligible = [item for item in eligible if item.source_id in sources]
    identities = source_identities(eligible, sources)

    if claim.kind == "numeric":
        if claim.numeric is None or not claim.numeric.value_text.strip():
            issues.append(_issue("numeric_value_missing", "Numeric Claim 缺少数值"))
        else:
            if not claim.numeric.unit:
                issues.append(_issue("numeric_unit_missing", "数值缺少单位"))
            if not claim.numeric.scope:
                issues.append(_issue("numeric_scope_missing", "数值缺少统计口径"))
            if not claim.numeric.time_basis:
                issues.append(
                    _issue("numeric_time_basis_missing", "数值缺少时间基础")
                )

    if claim.importance == "key" and eligible:
        qualified = [
            item
            for item in eligible
            if sources[item.source_id].source_kind in QUALIFIED_SOURCE_KINDS
        ]
        authoritative = [
            item
            for item in qualified
            if sources[item.source_id].source_kind
            in AUTHORITATIVE_SOURCE_KINDS
        ]
        qualified_identities = source_identities(qualified, sources)
        # 数值完整性由上面的专用 issue 阻断；这里仅判断来源门槛，
        # 避免对同一缺陷同时报告“字段缺失”和“来源不足”。
        authoritative_sufficient = bool(authoritative)
        if not qualified:
            issues.append(
                _issue(
                    "source_quality_insufficient",
                    "关键 Claim 缺少合格来源",
                )
            )
        elif not authoritative_sufficient and len(qualified_identities) < 2:
            issues.append(
                _issue(
                    "source_independence_insufficient",
                    "关键 Claim 缺少两个独立合格来源",
                )
            )

    return RuleCheckResult(
        eligible_evidence_ids=[item.evidence_id for item in eligible],
        source_identities=identities,
        issues=issues,
    )
