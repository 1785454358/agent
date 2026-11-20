"""Visible reference drafts and host-resolved, verbatim finding supports."""

import json
from collections import Counter
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeptrace.domain.evidence import EvidenceSupport, Finding
from deeptrace.domain.research_record import StudyIdentity
from deeptrace.research.observations import ExperimentDraft, resolve_experiments
from deeptrace.strategies.publication_dates import (
    is_declared_review,
    source_is_news,
    visible_publication_dates,
)
from deeptrace.tools.evidence_views import EvidencePassage


class ReferenceSupportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str = Field(pattern=r"^[pg][1-9][0-9]{0,2}$")


class ReferenceDateSupportDraft(ReferenceSupportDraft):
    """Dates must identify an exact visible quote, not a whole reading group."""

    ref: str = Field(pattern=r"^p[1-9][0-9]{0,2}$")


class ResearchResultDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "original_theory",
        "original_experiment",
        "method",
        "review",
        "background",
        "unknown",
    ]
    title: str = Field(min_length=1, max_length=300)
    published_on: date
    date_refs: list[ReferenceDateSupportDraft] = Field(min_length=1, max_length=2)

    @field_validator("date_refs", mode="before")
    @classmethod
    def normalize_reference_shape(cls, value):
        # Accept the initial string representation without guessing identifiers.
        return (
            [{"ref": ref} if isinstance(ref, str) else ref for ref in value]
            if isinstance(value, list)
            else value
        )


class ReferenceFindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=128)
    claim: str = Field(min_length=1, max_length=3000)
    confidence: float = Field(ge=0, le=1)
    supports: list[ReferenceSupportDraft] = Field(default_factory=list, max_length=3)
    research_result: ResearchResultDraft | None = None
    experiments: list[ExperimentDraft] = Field(default_factory=list, max_length=2)


class ReferenceSourceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(pattern=r"^s(?:[1-9]|[12][0-9]|3[0-2])$")
    status: Literal["eligible", "ineligible", "uncertain"]
    reason: str = Field(min_length=1, max_length=500)
    basis: Literal["user_restriction", "relevance", "reliability", "freshness"] | None = None
    restriction_quote: str | None = Field(default=None, min_length=1, max_length=500)


def parse_reference_evaluation(schema: type[BaseModel], text: str) -> BaseModel:
    """Normalize known transport/placement mistakes, then validate strictly."""
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return schema.model_validate_json(text)
    # Some providers echo response_format inside an otherwise valid assessment.
    # This exact transport marker carries no evidence or admission authority.
    if (
        isinstance(payload, dict)
        and "type" not in schema.model_fields
        and payload.get("type") == "json_object"
    ):
        payload.pop("type")
    coverage = payload.get("coverage") if isinstance(payload, dict) else None
    if isinstance(coverage, dict):
        for key in ("unresolved_gaps", "source_checks", "action", "reason", "sufficient", "recovery_tasks", "unchanged_requirement_ids"):
            # Never choose between contradictory root and nested values.
            if (
                key in schema.model_fields and key in coverage
                and (key not in payload or payload[key] == coverage[key])
            ):
                payload[key] = coverage.pop(key)
    return schema.model_validate(payload)


def normalize_source_checks(
    checks: list[ReferenceSourceCheck],
    source_ids: dict[str, str],
    visible_refs: dict[str, EvidencePassage],
    *, user_texts: list[str] | None = None,
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
        elif check.status != "eligible" and check.basis == "user_restriction" and (
            not check.restriction_quote
            or not any(check.restriction_quote in text for text in user_texts or [])
        ):
            issues.append(f"unauthorized_source_restriction:{identity}")
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
    *,
    source_policy: str = "general",
    publication_years: list[int] | None = None,
    cutoff: date | None = None,
    news_source_ids: set[str] | None = None,
    support_groups: dict[str, tuple[str, ...]] | None = None,
) -> tuple[list[Finding], list[str]]:
    counts = Counter(draft.id for draft in drafts)
    findings, diagnostics = [], []
    for draft in drafts:
        if counts[draft.id] != 1:
            diagnostics.append("duplicate_finding_id")
            continue
        supports = []
        for item in draft.supports:
            members = (support_groups or {}).get(item.ref, ()) if item.ref.startswith("g") else (item.ref,)
            passages = [visible_refs.get(ref) for ref in members]
            if not passages or any(p is None for p in passages) or len({
                (p.evidence_id, p.version, p.content_hash) for p in passages if p
            }) != 1:
                diagnostics.append("invalid_support_reference")
                continue
            for passage in passages:
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
            if source_policy == "research_results":
                result = draft.research_result
                supported_ids = {s.evidence_id for s in supports}
                dates = (
                    [visible_refs.get(ref.ref) for ref in result.date_refs]
                    if result
                    else []
                )
                news_ids = (news_source_ids or set()) | {
                    identity for identity in supported_ids if source_is_news(
                        "\n".join(p.text for p in visible_refs.values() if p.evidence_id == identity)
                    )
                }
                valid = (
                    result is not None
                    and result.kind
                    in {"original_theory", "original_experiment", "method"}
                    and not is_declared_review(
                        "\n".join(
                            p.text
                            for p in visible_refs.values()
                            if p.evidence_id in supported_ids
                        )
                    )
                    and (
                        not publication_years
                        or result.published_on.year in publication_years
                    )
                    and (cutoff is None or result.published_on <= cutoff)
                    and all(
                        p is not None and p.evidence_id in supported_ids for p in dates
                    )
                    and result.published_on
                    in {
                        day for p in dates if p for day in visible_publication_dates(
                            p.text, source_is_news_page=p.evidence_id in news_ids
                        )
                    }
                )
                if not valid:
                    diagnostics.append(f"invalid_research_result:{draft.id}")
                    continue
                for passage in dates:
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
            references = {}
            for ref, passage in visible_refs.items():
                references[ref] = [EvidenceSupport(evidence_id=passage.evidence_id,
                    version=passage.version, content_hash=passage.content_hash,
                    start=passage.start, end=passage.end, quote=passage.text)]
            for ref, members in (support_groups or {}).items():
                if members and all(member in references for member in members):
                    references[ref] = [s for member in members for s in references[member]]
            experiments, issues = resolve_experiments(draft.experiments, references, supports)
            diagnostics.extend(f"{issue}:{draft.id}" for issue in issues)
            findings.append(
                Finding(
                    id=draft.id,
                    claim=draft.claim,
                    confidence=draft.confidence,
                    evidence_ids=list(dict.fromkeys(s.evidence_id for s in supports)),
                    supports=supports,
                    research_result=StudyIdentity.model_validate(draft.research_result.model_dump(exclude={"date_refs"}))
                    if draft.research_result and source_policy == "research_results" else None,
                    experiments=experiments,
                )
            )
    return findings, list(dict.fromkeys(diagnostics))
