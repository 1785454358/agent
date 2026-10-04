"""Visible reference drafts and host-resolved, verbatim finding supports."""

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deeptrace.domain.evidence import EvidenceSupport, Finding
from deeptrace.tools.evidence_views import EvidencePassage


class ReferenceSupportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str = Field(pattern=r"^p[1-9][0-9]{0,2}$")


class ReferenceFindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=128)
    claim: str = Field(min_length=1, max_length=3000)
    confidence: float = Field(ge=0, le=1)
    supports: list[ReferenceSupportDraft] = Field(default_factory=list, max_length=3)


class ReferenceSourceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(pattern=r"^s[1-8]$")
    status: Literal["eligible", "ineligible", "uncertain"]
    reason: str = Field(min_length=1, max_length=500)


def normalize_source_checks(
    checks: list[ReferenceSourceCheck],
    source_ids: dict[str, str],
    visible_refs: dict[str, EvidencePassage],
) -> tuple[dict[str, str], list[str]]:
    """Resolve current source labels; missing/ambiguous checks never grant admission."""
    counts = Counter(check.source for check in checks)
    visible = {p.evidence_id for p in visible_refs.values()}
    result = dict.fromkeys(source_ids.values(), "uncertain")
    issues = []
    for check in checks:
        identity = source_ids.get(check.source)
        if identity is None:
            issues.append("unknown_source_check")
        elif counts[check.source] != 1:
            issues.append(f"duplicate_source_check:{identity}")
        elif identity not in visible:
            issues.append(f"source_check_without_visible_text:{identity}")
        else:
            result[identity] = check.status
            if check.status != "eligible":
                issues.append(f"source_{check.status}:{identity}:{check.reason}")
    issues.extend(
        f"missing_source_check:{identity}"
        for label, identity in source_ids.items()
        if label not in counts
    )
    return result, list(dict.fromkeys(issues))


def normalize_reference_findings(
    drafts: list[ReferenceFindingDraft],
    visible_refs: dict[str, EvidencePassage],
) -> tuple[list[Finding], list[str]]:
    counts = Counter(draft.id for draft in drafts)
    findings, diagnostics = [], []
    for draft in drafts:
        if counts[draft.id] != 1:
            diagnostics.append("duplicate_finding_id")
            continue
        supports = []
        for item in draft.supports:
            passage = visible_refs.get(item.ref)
            if passage is None:
                diagnostics.append("invalid_support_reference")
                continue
            support = EvidenceSupport(
                evidence_id=passage.evidence_id,
                version=passage.version,
                content_hash=passage.content_hash,
                start=passage.start,
                end=passage.end,
                quote=passage.text,
            )
            if support not in supports:
                supports.append(support)
        if supports:
            findings.append(
                Finding(
                    id=draft.id,
                    claim=draft.claim,
                    confidence=draft.confidence,
                    evidence_ids=list(dict.fromkeys(s.evidence_id for s in supports)),
                    supports=supports,
                )
            )
    return findings, list(dict.fromkeys(diagnostics))
