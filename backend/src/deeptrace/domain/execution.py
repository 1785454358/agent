from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from deeptrace.domain.conversation import ConversationSummary
from deeptrace.domain.evidence import Finding


class ResearchProfile(StrEnum):
    WORKFLOW = "workflow"
    PLAN_EXECUTE = "plan_execute"
    MULTI_AGENT = "multi_agent"


_LEGACY_PROFILES = {
    "basic": ResearchProfile.WORKFLOW,
    "deep": ResearchProfile.PLAN_EXECUTE,
}


def normalize_research_profile(value: str | ResearchProfile) -> ResearchProfile:
    if isinstance(value, ResearchProfile):
        return value
    candidate = value.strip().lower()
    if candidate in _LEGACY_PROFILES:
        return _LEGACY_PROFILES[candidate]
    try:
        return ResearchProfile(candidate)
    except ValueError as exc:
        raise ValueError(f"unknown research profile: {value}") from exc


class ResponseProfile(StrEnum):
    ANSWER = "answer"
    BRIEF = "brief"
    REPORT = "report"


class ConversationIntent(StrEnum):
    CONVERSATION = "conversation"
    CLARIFICATION = "clarification"
    RESEARCH = "research"
    INCREMENTAL_RESEARCH = "incremental_research"
    SWITCH_PROFILE = "switch_profile"
    REPORT_REQUEST = "report_request"
    MEMORY_UPDATE = "memory_update"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorCategory(StrEnum):
    TRANSIENT = "transient"
    VALIDATION = "validation"
    POLICY = "policy"
    AGENT_RECOVERABLE = "agent_recoverable"
    PARTIAL = "partial"
    FATAL = "fatal"
    CANCELLED = "cancelled"


class BudgetSnapshot(BaseModel):
    max_model_calls: int = Field(default=0, ge=0)
    max_tool_calls: int = Field(default=0, ge=0)
    max_network_requests: int = Field(default=0, ge=0)
    used_model_calls: int = Field(default=0, ge=0)
    used_tool_calls: int = Field(default=0, ge=0)
    used_network_requests: int = Field(default=0, ge=0)


class ErrorRecord(BaseModel):
    code: str = Field(min_length=1)
    category: ErrorCategory
    retryable: bool = False
    source: str = Field(min_length=1)
    node: str = Field(min_length=1)
    attempt: int = Field(default=1, ge=1)
    public_message: str = Field(min_length=1)
    internal_detail: str | None = None


class ResearchInput(BaseModel):
    question: str = Field(min_length=1)
    conversation_summary: ConversationSummary = Field(
        default_factory=ConversationSummary
    )
    prior_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    budget: BudgetSnapshot = Field(default_factory=BudgetSnapshot)
    current_date: str
    timezone: str


class ResearchOutcome(BaseModel):
    profile: ResearchProfile
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    executed_steps: int = Field(ge=0)
    termination_reason: str = Field(min_length=1)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value
