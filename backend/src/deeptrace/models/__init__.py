"""DeepTrace 跨模块共享的强类型数据模型。"""

from deeptrace.models.document import (
    DocumentChunk,
    PendingFetch,
    RawDocument,
    ScraperUsed,
)
from deeptrace.models.evidence import (
    Claim,
    ClaimImportance,
    ClaimKind,
    Evidence,
    EvidenceLocationStatus,
    NumericDetail,
    Source,
    SourceChannel,
)
from deeptrace.models.metrics import (
    ContextAudit,
    PageCompressionMetrics,
    RoundTokenMetrics,
    TokenUsage,
    UsageBreakdown,
    add_token_usages,
)
from deeptrace.models.plan import ResearchPlan, ResearchTask, ResearchTimeRange
from deeptrace.models.quality import SourceKind, TemporalRelation
from deeptrace.models.report import (
    RunEvent,
    SectionResult,
    TaskCompletion,
    TaskCoverage,
    TaskStatus,
)
from deeptrace.models.research import CompressionOutcome, ResearchNote
from deeptrace.models.verification import (
    EvidenceAssessment,
    EvidenceRelation,
    GapPriority,
    IssueSeverity,
    TaskVerificationSummary,
    VerificationGap,
    VerificationIssue,
    VerificationResult,
    VerificationVerdict,
)

__all__ = [
    "Claim",
    "ClaimImportance",
    "ClaimKind",
    "CompressionOutcome",
    "ContextAudit",
    "DocumentChunk",
    "Evidence",
    "EvidenceAssessment",
    "EvidenceLocationStatus",
    "EvidenceRelation",
    "GapPriority",
    "IssueSeverity",
    "NumericDetail",
    "PageCompressionMetrics",
    "PendingFetch",
    "RawDocument",
    "ResearchNote",
    "ResearchPlan",
    "ResearchTask",
    "ResearchTimeRange",
    "SourceKind",
    "TemporalRelation",
    "RoundTokenMetrics",
    "RunEvent",
    "ScraperUsed",
    "SectionResult",
    "Source",
    "SourceChannel",
    "TaskCompletion",
    "TaskCoverage",
    "TaskStatus",
    "TaskVerificationSummary",
    "TokenUsage",
    "UsageBreakdown",
    "VerificationGap",
    "VerificationIssue",
    "VerificationResult",
    "VerificationVerdict",
    "add_token_usages",
]
