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
from deeptrace.models.research import CompressionOutcome, ResearchNote

__all__ = [
    "CompressionOutcome",
    "ContextAudit",
    "DocumentChunk",
    "PageCompressionMetrics",
    "PendingFetch",
    "RawDocument",
    "ResearchNote",
    "RoundTokenMetrics",
    "ScraperUsed",
    "TokenUsage",
]
