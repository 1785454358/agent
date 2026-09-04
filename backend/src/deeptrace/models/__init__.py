"""DeepTrace 跨模块共享的强类型数据模型。"""

from deeptrace.models.document import (
    DocumentChunk,
    PendingFetch,
    RawDocument,
    ScraperUsed,
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

__all__ = [
    "CompressionOutcome",
    "ContextAudit",
    "DocumentChunk",
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
    "TaskCompletion",
    "TaskCoverage",
    "TaskStatus",
    "TokenUsage",
    "UsageBreakdown",
    "add_token_usages",
]
