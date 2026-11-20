"""An immutable, host-verifiable projection of sources, spans and claims."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from deeptrace.domain.coverage import CoverageAssessment
from deeptrace.domain.evidence import (
    CanonicalUrl,
    ContentHash,
    Evidence,
    EvidenceIdentifier,
    EvidenceLifecycleStatus,
    EvidenceSupport,
    EvidenceTitle,
    Finding,
)


class ClaimStatus(StrEnum):
    UNVERIFIED = "unverified"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


ClaimText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)
]
IssueText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
RequirementId = Annotated[str, StringConstraints(pattern=r"^r[1-6]$")]


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_url: CanonicalUrl
    title: EvidenceTitle
    source_quality: float = Field(ge=0.0, le=1.0)


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EvidenceIdentifier
    evidence_id: EvidenceIdentifier
    version: int = Field(ge=1)
    content_hash: ContentHash
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    quote: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_range(self) -> EvidenceSpan:
        if self.end <= self.start or self.end - self.start != len(self.quote):
            raise ValueError("span_range_mismatch")
        return self

    @classmethod
    def from_support(cls, support: EvidenceSupport) -> EvidenceSpan:
        identity = "\0".join(
            (
                support.evidence_id,
                str(support.version),
                support.content_hash,
                str(support.start),
                str(support.end),
                support.quote,
            )
        )
        return cls(
            id="span-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
            **support.model_dump(),
        )


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EvidenceIdentifier
    text: ClaimText
    confidence: float = Field(ge=0.0, le=1.0)
    requirement_ids: tuple[RequirementId, ...] = Field(default_factory=tuple, max_length=6)
    support_span_ids: tuple[EvidenceIdentifier, ...] = Field(default_factory=tuple, max_length=128)
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    issues: tuple[IssueText, ...] = Field(default_factory=tuple, max_length=16)

    @field_validator("requirement_ids", "support_span_ids")
    @classmethod
    def unique_references(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must be unique")
        return value


class EvidenceGraph(BaseModel):
    """Graph nodes are values; accepted claims are the only writer inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sources: tuple[EvidenceSource, ...] = Field(default_factory=tuple, max_length=100)
    evidence: tuple[Evidence, ...] = Field(default_factory=tuple, max_length=100)
    spans: tuple[EvidenceSpan, ...] = Field(default_factory=tuple, max_length=12800)
    claims: tuple[Claim, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def unique_nodes(self) -> EvidenceGraph:
        if len({record.id for record in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate_evidence_id")
        if len({span.id for span in self.spans}) != len(self.spans):
            raise ValueError("duplicate_span_id")
        if len({claim.id for claim in self.claims}) != len(self.claims):
            raise ValueError("duplicate_claim_id")
        record_by_id = {record.id: record for record in self.evidence}
        span_by_id = {span.id: span for span in self.spans}
        for claim in self.claims:
            missing = set(claim.support_span_ids) - set(span_by_id)
            if missing:
                raise ValueError("claim references an unavailable evidence span")
            if claim.status is not ClaimStatus.ACCEPTED:
                continue
            if not claim.support_span_ids or claim.issues:
                raise ValueError("accepted_claim_must_have_clean_supports")
            for span_id in claim.support_span_ids:
                span = span_by_id[span_id]
                record = record_by_id.get(span.evidence_id)
                if record is None:
                    raise ValueError("accepted_claim_references_unavailable_evidence")
                if (span.version, span.content_hash) != (
                    record.version,
                    record.content_hash,
                ):
                    raise ValueError("accepted_claim_span_does_not_match_evidence")
                if record.status is not EvidenceLifecycleStatus.ACTIVE:
                    raise ValueError("accepted_claim_requires_active_evidence")
        return self

    @property
    def accepted_claims(self) -> tuple[Claim, ...]:
        return tuple(claim for claim in self.claims if claim.status is ClaimStatus.ACCEPTED)


def _support_issue(
    support: EvidenceSupport,
    *,
    records: Mapping[str, Evidence],
    bodies: Mapping[str, str],
    eligibility: Mapping[str, str] | None,
) -> str | None:
    record = records.get(support.evidence_id)
    if record is None:
        return "evidence_unavailable"
    if record.status is not EvidenceLifecycleStatus.ACTIVE:
        return "evidence_not_active"
    if support.version != record.version:
        return "evidence_version_mismatch"
    if support.content_hash != record.content_hash:
        return "evidence_hash_mismatch"
    if eligibility is None:
        return "source_eligibility_unavailable"
    if eligibility.get(record.id, "uncertain") != "eligible":
        return "source_ineligible_or_uncertain"
    body = bodies.get(record.id)
    if body is None:
        return "body_unavailable"
    if support.end > len(body) or body[support.start : support.end] != support.quote:
        return "quote_mismatch"
    return None


def build_evidence_graph(
    *,
    evidence: Iterable[Evidence],
    bodies: Mapping[str, str],
    findings: Iterable[Finding],
    source_eligibility: Mapping[str, str] | None,
    coverage: CoverageAssessment | None = None,
) -> EvidenceGraph:
    """Project legacy findings into claims; never mint evidence from claims."""
    records = tuple(evidence)
    record_by_id = {record.id: record for record in records}
    if len(record_by_id) != len(records):
        raise ValueError("duplicate_evidence_id")
    source_records: dict[str, Evidence] = {}
    for record in records:
        current = source_records.get(record.canonical_url)
        activates_source = (
            current is not None
            and current.status is not EvidenceLifecycleStatus.ACTIVE
            and record.status is EvidenceLifecycleStatus.ACTIVE
        )
        newer_same_status = (
            current is not None
            and current.status is record.status
            and record.version > current.version
        )
        if current is None or activates_source or newer_same_status:
            source_records[record.canonical_url] = record
    sources = tuple(
        EvidenceSource(
            canonical_url=record.canonical_url,
            title=record.title,
            source_quality=record.source_quality,
        )
        for record in source_records.values()
    )
    requirement_by_claim: dict[str, list[str]] = {}
    if coverage is not None:
        for item in coverage.items:
            for finding_id in item.finding_ids:
                requirement_by_claim.setdefault(finding_id, []).append(item.requirement_id)

    spans: dict[str, EvidenceSpan] = {}
    claims: list[Claim] = []
    for finding in findings:
        finding_spans = [EvidenceSpan.from_support(support) for support in finding.supports]
        for span in finding_spans:
            if span.id not in spans:
                spans[span.id] = span
        issues = list(
            dict.fromkeys(
                issue
                for support in finding.supports
                if (issue := _support_issue(
                    support,
                    records=record_by_id,
                    bodies=bodies,
                    eligibility=source_eligibility,
                ))
                is not None
            )
        )[:16]
        accepted = bool(finding.supports) and not issues
        claims.append(
            Claim(
                id=finding.id,
                text=finding.claim,
                confidence=finding.confidence,
                requirement_ids=tuple(requirement_by_claim.get(finding.id, [])),
                support_span_ids=tuple(span.id for span in finding_spans),
                status=(ClaimStatus.ACCEPTED if accepted else ClaimStatus.UNVERIFIED),
                issues=tuple(issues),
            )
        )
    return EvidenceGraph(
        sources=sources,
        evidence=records,
        spans=tuple(spans.values()),
        claims=tuple(claims),
    )
