"""Application-facing projection of one authoritative Harness terminal turn."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deeptrace.domain import ResearchOutcome, ResponseOutcome
from deeptrace.domain.execution import ExecutionIdentifier


class ApplicationRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: ExecutionIdentifier
    thread_id: ExecutionIdentifier
    status: Literal["completed", "partial"]
    response_outcome: ResponseOutcome
    research_outcome: ResearchOutcome | None
    termination_reason: str = Field(min_length=1)
    executed_steps: int = Field(ge=0)
    unresolved_gaps: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
