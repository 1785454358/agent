"""阶段 4 的主张核验结果模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from deeptrace.models.quality import SourceKind


VerificationVerdict = Literal[
    "verified",
    "partially_supported",
    "unsupported",
    "conflicted",
    "out_of_range",
]
EvidenceRelation = Literal["supports", "refutes", "unrelated"]
IssueSeverity = Literal["warning", "blocking"]
GapPriority = Literal["high", "medium", "low"]


class EvidenceAssessment(BaseModel):
    """一条证据对某个主张的作用。"""

    evidence_id: str = Field(min_length=1)
    relation: EvidenceRelation
    reason: str = Field(min_length=1)


class VerificationIssue(BaseModel):
    """核验过程中发现的问题。"""

    code: str = Field(min_length=1)
    severity: IssueSeverity = "warning"
    message: str = Field(min_length=1)


class VerificationResult(BaseModel):
    """单个主张的完整核验结果。"""

    claim_id: str = Field(min_length=1)
    verdict: VerificationVerdict
    reason: str = Field(min_length=1)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    refuting_evidence_ids: list[str] = Field(default_factory=list)
    source_identities: list[str] = Field(default_factory=list)
    assessments: list[EvidenceAssessment] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    verified_at: datetime


class VerificationGap(BaseModel):
    """需要补充检索的证据缺口。"""

    gap_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    priority: GapPriority = "medium"
    preferred_source_kinds: list[SourceKind] = Field(default_factory=list)


class TaskVerificationSummary(BaseModel):
    """研究子任务的核验汇总。"""

    task_id: str = Field(min_length=1)
    verified_claim_ids: list[str] = Field(default_factory=list)
    partial_claim_ids: list[str] = Field(default_factory=list)
    unsupported_claim_ids: list[str] = Field(default_factory=list)
    conflicted_claim_ids: list[str] = Field(default_factory=list)
    supplement_rounds: int = Field(default=0, ge=0)
