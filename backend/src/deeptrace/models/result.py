"""AgentResult：所有研究模式共用的运行结果类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from deeptrace.domain.run import (
    FinishReason,
    ResearchSufficiency,
    TerminalStatus,
    normalize_finish_reason,
)

from deeptrace.models.metrics import TokenUsage, UsageBreakdown
from deeptrace.models.report import RunEvent


@dataclass(frozen=True)
class AgentResult:
    """The final public result of one research run."""

    status: TerminalStatus
    answer: str
    sources: list[str]
    steps: int
    events: list[RunEvent]
    termination_reason: str
    search_queries: list[str]
    provider_usage: TokenUsage
    role_usage: UsageBreakdown
    estimated_cost_usd: Decimal | None
    stage_seconds: dict[str, float]
    unresolved_gaps: list[str] = field(default_factory=list)
    usage_observation: dict[str, Any] | None = None
    research_sufficiency: ResearchSufficiency = ResearchSufficiency.UNKNOWN

    @property
    def finish_reason(self) -> FinishReason:
        return normalize_finish_reason(self.termination_reason)
