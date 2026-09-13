"""Relational schema for research run lifecycle data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, JSON, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ResearchRunRow(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    thread_id: Mapped[str] = mapped_column(String(128), default="")
    termination_reason: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answer: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    search_queries: Mapped[list[str]] = mapped_column(JSON, default=list)
    unresolved_gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunEventRow(Base):
    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_run_id_id", "run_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CheckpointRow(Base):
    __tablename__ = "graph_checkpoints"
    __table_args__ = (
        Index(
            "ux_graph_checkpoints_identity",
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(256), default="")
    checkpoint_id: Mapped[str] = mapped_column(String(64))
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[str | None] = mapped_column(String(64))
    checkpoint_blob: Mapped[bytes] = mapped_column(LargeBinary)
    metadata_blob: Mapped[bytes] = mapped_column(LargeBinary)
    metadata_type: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CheckpointWriteRow(Base):
    __tablename__ = "graph_checkpoint_writes"
    __table_args__ = (
        Index(
            "ix_graph_writes_task",
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            "task_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(256), default="")
    checkpoint_id: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str] = mapped_column(String(64))
    task_path: Mapped[str] = mapped_column(String(256), default="")
    idx: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(128))
    type: Mapped[str | None] = mapped_column(String(64))
    blob: Mapped[bytes | None] = mapped_column(LargeBinary)


class ToolExecutionRow(Base):
    __tablename__ = "tool_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128))
    run_id: Mapped[str] = mapped_column(String(128))
    call_id: Mapped[str] = mapped_column(String(160))
    fingerprint: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="running")
    generation: Mapped[int] = mapped_column(Integer, default=1)
    owner_token: Mapped[str | None] = mapped_column(String(64))
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "ux_tool_executions_identity",
            "tenant_id",
            "run_id",
            "call_id",
            unique=True,
        ),
    )


class MemoryRecordRow(Base):
    __tablename__ = "memory_records"
    __table_args__ = (Index("ux_memory_records_key", "namespace_scope", "namespace_owner", "namespace_kind", "store_key", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    namespace_scope: Mapped[str] = mapped_column(String(32))
    namespace_owner: Mapped[str] = mapped_column(String(128))
    namespace_kind: Mapped[str] = mapped_column(String(64))
    store_key: Mapped[str] = mapped_column(String(512))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
