"""Serializable lifecycle models for local and distributed research runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from deeptrace.domain.execution import normalize_mode_selection, ResearchMode
from deeptrace.domain.run import (
    TERMINAL_STATUSES,
    FinishReason,
    ResearchSufficiency,
    TerminalStatus,
    normalize_finish_reason,
)

RunMode = Literal["auto", "workflow", "plan_execute", "multi_agent", "basic", "deep"]
_CONCRETE_MODE_VALUES = frozenset(mode.value for mode in ResearchMode)
RunStatus = TerminalStatus | Literal[
    "pending",
    "running",
    "cancel_requested",
]


class RunRecord(BaseModel):
    """Durable public state for one research execution."""

    id: str
    question: str
    mode: RunMode = "workflow"
    status: RunStatus = "pending"
    thread_id: str = ""
    termination_reason: str = ""
    research_sufficiency: ResearchSufficiency = ResearchSufficiency.UNKNOWN
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None
    answer: str = ""
    sources: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    error: str | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    attempt_count: int = 0
    version: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None

    @computed_field
    @property
    def finish_reason(self) -> FinishReason | None:
        if self.status not in TERMINAL_STATUSES:
            return None
        return normalize_finish_reason(self.termination_reason)

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_legacy_mode(cls, value: object) -> object:
        """Legacy persisted aliases read back as canonical values."""
        if isinstance(value, str):
            return str(normalize_mode_selection(value))
        return value

    def routing_metadata(self) -> dict[str, str | None]:
        """Project the durable decision without adding SQL lifecycle columns."""
        for event in reversed(self.events):
            details = event.get("details") or {}
            selected = details.get("mode")
            if event.get("event_type") == "research.routed" and isinstance(selected, str) and selected in _CONCRETE_MODE_VALUES:
                return {"selected_mode": str(details["mode"]), "routing_reason": details.get("reason")}
        return {"selected_mode": self.mode if self.mode != "auto" else None, "routing_reason": None}


class StoredEvent(BaseModel):
    """One monotonically ordered event persisted for SSE replay."""

    id: int
    run_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class JobMessage(BaseModel):
    """A Redis Stream delivery identifying the run to execute."""

    message_id: str
    run_id: str
