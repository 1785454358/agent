"""LLM 语义核验与不可覆盖的本地判定合并。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import json_repair
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from deeptrace.agent._shared import add_usage, message_text, message_usage
from deeptrace.models import (
    Claim,
    Evidence,
    EvidenceAssessment,
    ResearchTimeRange,
    Source,
    TokenUsage,
    VerificationIssue,
    VerificationResult,
)
from deeptrace.prompts.verifier import build_verifier_messages
from deeptrace.verification.rules import RuleCheckResult, check_claim_rules


class VerifierClaimDraft(BaseModel):
    claim_id: str
    assessments: list[EvidenceAssessment] = Field(default_factory=list)
    reason: str = ""


class VerifierDraft(BaseModel):
    claims: list[VerifierClaimDraft] = Field(default_factory=list)


def parse_verifier_draft(raw: str) -> VerifierDraft:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Verifier 未返回 JSON 对象")
    try:
        payload = json_repair.loads(raw[start : end + 1])
        return VerifierDraft.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"Verifier JSON 无法校验：{exc}") from exc


def merge_verdict(
    *,
    claim: Claim,
    rules: RuleCheckResult,
    assessments: Sequence[EvidenceAssessment],
    provider_error: str | None,
) -> VerificationResult:
    """本地规则拥有否决权，LLM 只能在门槛内完成语义判定。"""
    if rules.forced_verdict is not None:
        return VerificationResult(
            claim_id=claim.claim_id,
            verdict=rules.forced_verdict,
            reason="确定性规则直接判定",
            source_identities=rules.source_identities,
            issues=rules.issues,
            verified_at=datetime.now(UTC),
        )

    supports = [
        item.evidence_id
        for item in assessments
        if item.relation == "supports"
    ]
    refutes = [
        item.evidence_id
        for item in assessments
        if item.relation == "refutes"
    ]
    issues = list(rules.issues)
    if provider_error:
        issues.append(
            VerificationIssue(
                code="verifier_error",
                severity="warning",
                message=provider_error,
            )
        )

    has_blocking = bool(rules.blocking_issues)
    if supports and refutes:
        verdict = "conflicted"
        reason = "现有证据同时包含直接支持和直接反驳"
    elif provider_error:
        verdict = (
            "partially_supported"
            if rules.eligible_evidence_ids
            else "unsupported"
        )
        reason = "语义核验失败，未将本地规则升级为已验证"
    elif supports and not has_blocking:
        verdict = "verified"
        reason = "直接支持证据通过本地资格与来源门槛"
    elif supports:
        verdict = "partially_supported"
        reason = "存在直接支持，但仍有不可覆盖的本地阻断问题"
    else:
        verdict = "unsupported"
        reason = "没有可确认的直接支持证据"

    return VerificationResult(
        claim_id=claim.claim_id,
        verdict=verdict,
        reason=reason,
        supporting_evidence_ids=list(dict.fromkeys(supports)),
        refuting_evidence_ids=list(dict.fromkeys(refutes)),
        source_identities=rules.source_identities,
        assessments=list(assessments),
        issues=issues,
        verified_at=datetime.now(UTC),
    )


class VerifierAgent:
    """批量语义核验；无效输出只重试一次且永不失败升级。"""

    def __init__(self, model: Any, *, timeout_seconds: float = 60.0) -> None:
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def averify(
        self,
        claims: Sequence[Claim],
        evidence: Mapping[str, Evidence],
        sources: Mapping[str, Source],
        time_range: ResearchTimeRange | None,
    ) -> tuple[dict[str, VerificationResult], TokenUsage]:
        rules = {
            claim.claim_id: check_claim_rules(
                claim, evidence, sources, time_range
            )
            for claim in claims
        }
        return await self.averify_with_rules(
            claims, evidence, sources, time_range, rules
        )

    async def averify_with_rules(
        self,
        claims: Sequence[Claim],
        evidence: Mapping[str, Evidence],
        sources: Mapping[str, Source],
        time_range: ResearchTimeRange | None,
        rules: Mapping[str, RuleCheckResult],
    ) -> tuple[dict[str, VerificationResult], TokenUsage]:
        del time_range
        total = TokenUsage()
        result: dict[str, VerificationResult] = {}
        pending = [
            claim
            for claim in claims
            if rules[claim.claim_id].forced_verdict is None
        ]
        for claim in claims:
            rule = rules[claim.claim_id]
            if rule.forced_verdict is not None:
                result[claim.claim_id] = merge_verdict(
                    claim=claim,
                    rules=rule,
                    assessments=[],
                    provider_error=None,
                )
        if not pending:
            return result, total

        messages = build_verifier_messages(pending, evidence, sources, rules)
        validation_error = ""
        parsed: VerifierDraft | None = None
        provider_error: str | None = None
        for attempt in range(2):
            attempt_messages = list(messages)
            if attempt and validation_error:
                attempt_messages.append(
                    HumanMessage(
                        content=(
                            "上次输出校验失败，请只返回修正后的 JSON。"
                            f"校验错误：{validation_error}"
                        )
                    )
                )
            try:
                response = await asyncio.wait_for(
                    self._model.ainvoke(attempt_messages),
                    timeout=self._timeout_seconds,
                )
                total = add_usage(total, message_usage(response))
                parsed = parse_verifier_draft(message_text(response))
                provider_error = None
                break
            except Exception as exc:
                validation_error = str(exc)
                provider_error = f"{type(exc).__name__}: {exc}"

        drafts = {
            item.claim_id: item
            for item in (parsed.claims if parsed is not None else [])
        }
        for claim in pending:
            rule = rules[claim.claim_id]
            draft = drafts.get(claim.claim_id)
            allowed = set(rule.eligible_evidence_ids)
            assessments = [
                item
                for item in (draft.assessments if draft else [])
                if item.evidence_id in allowed
            ]
            missing_error = provider_error
            if parsed is not None and draft is None:
                missing_error = "Verifier 未返回该 Claim"
            result[claim.claim_id] = merge_verdict(
                claim=claim,
                rules=rule,
                assessments=assessments,
                provider_error=missing_error,
            )
        return result, total

