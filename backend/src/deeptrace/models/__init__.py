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
)
from deeptrace.models.plan import ResearchPlan, ResearchTask, ResearchTimeRange
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
    "RoundTokenMetrics",
    "RunEvent",
    "ScraperUsed",
    "SectionResult",
    "TaskCompletion",
    "TaskCoverage",
    "TaskStatus",
    "TokenUsage",
]
