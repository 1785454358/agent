"""Serializable lifecycle models for local and distributed research runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RunMode = Literal["basic", "deep", "multi_agent"]
RunStatus = Literal[
    "pending",
    "running",
    "completed",
    "partial",
    "failed",
    "cancel_requested",
    "cancelled",
]


class RunRecord(BaseModel):
    """Durable public state for one research execution."""

    id: str
    question: str
    mode: RunMode = "basic"
    status: RunStatus = "pending"
    termination_reason: str = ""
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
