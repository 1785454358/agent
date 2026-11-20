"""The single, model-independent verification decision for a research run."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeptrace.domain.coverage import (
    CoverageAssessment,
    RequirementCoverage,
    ResearchRequirement,
    requirements_satisfied,
)
from deeptrace.domain.evidence import Evidence, Finding
from deeptrace.research.evidence_graph import (
    Claim,
    EvidenceGraph,
    build_evidence_graph,
)


class VerificationAction(StrEnum):
    CONTINUE = "continue"
    REPLAN = "replan"
    SYNTHESIZE = "synthesize"
    PARTIAL = "partial"
    STOP = "stop"


class VerificationResult(BaseModel):
    """Only accepted claims and their normalized coverage may gate completion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    graph: EvidenceGraph
    coverage: CoverageAssessment | None = None
    issues: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    recommended_action: VerificationAction
    reason: str = Field(min_length=1, max_length=500)
    required_requirement_ids: tuple[str,...] | None = None

    @field_validator("issues")
    @classmethod
    def bounded_issue_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for issue in value:
            if not issue.strip() or len(issue) > 500:
                raise ValueError("verification issues must be 1..500 characters")
        return value

    @property
    def coverage_complete(self) -> bool:
        required=self.required_requirement_ids
        return bool(self.coverage) and (required is None or bool(required)) and all(
            item.status=="covered" for item in self.coverage.items
            if required is None or item.requirement_id in required)

    @property
    def accepted_claims(self) -> tuple[Claim, ...]:
        return self.graph.accepted_claims

    @property
    def blocking_coverage(self) -> tuple[RequirementCoverage, ...]:
        return tuple(
            item
            for item in (self.coverage.items if self.coverage else ())
            if item.status != "covered" and (self.required_requirement_ids is None
                or item.requirement_id in self.required_requirement_ids)
        )


def verify_evidence_graph(
    graph: EvidenceGraph,
    requirements: Iterable[ResearchRequirement],
    *,
    submitted_coverage: CoverageAssessment | None = None,
    can_replan: bool = True,
) -> VerificationResult:
    """Normalize coverage against host-accepted claims, not model assertions."""
    requirements = tuple(requirements)
    submitted_by_id = (
        {item.requirement_id: item for item in submitted_coverage.items}
        if submitted_coverage is not None
        else {}
    )
    unknown_requirements = set(submitted_by_id) - {
        requirement.id for requirement in requirements
    }
    if unknown_requirements:
        raise ValueError("coverage references an unknown requirement")

    accepted_by_id = {claim.id: claim for claim in graph.accepted_claims}
    normalized_items: list[RequirementCoverage] = []
    for requirement in requirements:
        submitted = submitted_by_id.get(requirement.id)
        if submitted is None:
            normalized_items.append(
                RequirementCoverage(
                    requirement_id=requirement.id,
                    status="missing",
                    reason="requirement_not_evaluated",
                )
            )
            continue
        linked_accepted_claims = [
            claim_id
            for claim_id in submitted.finding_ids
            if claim_id in accepted_by_id
            and requirement.id in accepted_by_id[claim_id].requirement_ids
        ]
        if submitted.status == "covered" and (
            not linked_accepted_claims
            or len(linked_accepted_claims) != len(submitted.finding_ids)
        ):
            normalized_items.append(
                RequirementCoverage(
                    requirement_id=requirement.id,
                    status="missing",
                    reason="unsupported_requirement_coverage",
                )
            )
        else:
            normalized_items.append(
                submitted.model_copy(update={"finding_ids":linked_accepted_claims})
            )

    coverage = (
        CoverageAssessment(items=normalized_items) if normalized_items else None
    )
    issues = tuple(
        dict.fromkeys(
            f"claim:{claim.id}:{issue}"
            for claim in graph.claims
            for issue in claim.issues
        )
    )[:100]
    common = {
        "graph": graph,
        "coverage": coverage,
        "issues": issues,
        "required_requirement_ids":tuple(r.id for r in requirements if r.required),
    }
    if not requirements:
        return VerificationResult(
            **common,
            recommended_action=VerificationAction.PARTIAL,
            reason="no acceptance requirements were established",
        )
    if requirements_satisfied(requirements, coverage):
        return VerificationResult(
            **common,
            recommended_action=VerificationAction.SYNTHESIZE,
            reason="all acceptance requirements have host-verified supports",
        )
    if can_replan:
        return VerificationResult(
            **common,
            recommended_action=VerificationAction.REPLAN,
            reason="some acceptance requirements lack accepted support",
        )
    return VerificationResult(
        **common,
        recommended_action=VerificationAction.PARTIAL,
        reason="replans are exhausted; preserve verified partial results",
    )


def project_verification_result(
    *,
    evidence: Iterable[Evidence],
    bodies: Mapping[str, str],
    findings: Iterable[Finding],
    source_eligibility: Mapping[str, str] | None,
    requirements: Iterable[ResearchRequirement],
    coverage: CoverageAssessment | None = None,
    can_replan: bool = True,
) -> VerificationResult:
    """Build the new graph and verdict from the current evaluator's artifacts."""
    graph = build_evidence_graph(
        evidence=evidence,
        bodies=bodies,
        findings=findings,
        source_eligibility=source_eligibility,
        coverage=coverage,
    )
    return verify_evidence_graph(
        graph,
        requirements,
        submitted_coverage=coverage,
        can_replan=can_replan,
    )
