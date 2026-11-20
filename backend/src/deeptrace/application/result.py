"""Application-facing projection of one authoritative Harness terminal turn."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.domain import ResearchOutcome, ResponseOutcome
from deeptrace.domain.execution import ExecutionIdentifier
from deeptrace.domain.run import (
    FinishReason,
    ResearchSufficiency,
    TerminalStatus,
    normalize_finish_reason,
)


class ApplicationRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: ExecutionIdentifier
    thread_id: ExecutionIdentifier
    status: TerminalStatus
    response_outcome: ResponseOutcome | None
    research_outcome: ResearchOutcome | None
    termination_reason: str = Field(min_length=1)
    executed_steps: int = Field(ge=0)
    unresolved_gaps: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    research_sufficiency: ResearchSufficiency = ResearchSufficiency.UNKNOWN

    @property
    def finish_reason(self) -> FinishReason:
        return normalize_finish_reason(self.termination_reason)

    @model_validator(mode="after")
    def require_usable_response(self) -> ApplicationRunResult:
        if self.status in {"completed", "partial"} and self.response_outcome is None:
            raise ValueError("completed/partial results require a response outcome")
        return self
