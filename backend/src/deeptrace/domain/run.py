"""Terminal vocabulary shared by executors, applications and lifecycle adapters.

Lifecycle states such as running are deliberately absent from TerminalStatus.
Legacy detail strings remain authoritative; their normalized classification is
derived so historical runs do not need rewriting.
"""

from enum import StrEnum
from typing import Literal, get_args

TerminalStatus = Literal["completed", "partial", "failed", "cancelled"]
TERMINAL_STATUSES = frozenset(get_args(TerminalStatus))


class FinishReason(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ITERATION_LIMIT = "iteration_limit"
    PLANNING_LIMIT = "planning_limit"
    ERROR_LIMIT = "error_limit"
    CONTEXT_LIMIT = "context_limit"
    MODEL_ERROR = "model_error"
    TOOL_ERROR = "tool_error"
    RESPONSE_ERROR = "response_error"
    RUNTIME_ERROR = "runtime_error"
    INTERRUPTED = "interrupted"
    INCOMPLETE_PLAN = "incomplete_plan"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NO_PROGRESS = "no_progress"
    UNKNOWN = "unknown"


class ResearchSufficiency(StrEnum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"


_LEGACY_REASONS = {
    "workflow_completed": FinishReason.COMPLETED,
    "mode_switched": FinishReason.COMPLETED,
    "memory_updated": FinishReason.COMPLETED,
    "max_iterations": FinishReason.ITERATION_LIMIT,
    "max_replans_reached": FinishReason.PLANNING_LIMIT,
    "max_follow_ups_reached": FinishReason.PLANNING_LIMIT,
    "no_sources": FinishReason.INSUFFICIENT_EVIDENCE,
    "no_evidence": FinishReason.INSUFFICIENT_EVIDENCE,
    "no_research_progress": FinishReason.NO_PROGRESS,
    "worker_error": FinishReason.RUNTIME_ERROR,
    "citation_invalid": FinishReason.RESPONSE_ERROR,
    "no_supported_citations": FinishReason.RESPONSE_ERROR,
    "answer_review_incomplete": FinishReason.RESPONSE_ERROR,
    "answer_review_unavailable": FinishReason.RESPONSE_ERROR,
    "generation_failed": FinishReason.RESPONSE_ERROR,
    "response_context_limit": FinishReason.CONTEXT_LIMIT,
    "response_evidence_context_limit": FinishReason.CONTEXT_LIMIT,
    "memory_unavailable": FinishReason.RUNTIME_ERROR,
    "memory_rejected": FinishReason.PARTIAL,
}


def normalize_finish_reason(detail: str) -> FinishReason:
    """Classify known details; unfamiliar legacy values never imply success."""
    code = detail.partition(":")[0]
    if code in _LEGACY_REASONS:
        return _LEGACY_REASONS[code]
    try:
        return FinishReason(code)
    except ValueError:
        return FinishReason.UNKNOWN
