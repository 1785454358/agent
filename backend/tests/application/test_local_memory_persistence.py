from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from deeptrace.application.assembly import (
    _build_durable_stores,
    _ensure_sqlite_schema,
)
from deeptrace.config import Settings
from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType
from deeptrace.persistence.memory_store import SqlAlchemyMemoryStore


NOW = datetime(2026, 9, 15, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(
        openai_api_key="test-key",
        openai_base_url="http://127.0.0.1:1",
        openai_model="test-model",
        tavily_api_key="test-key",
    )


def _record() -> MemoryRecord:
    return MemoryRecord(
        type=MemoryType.FACT,
        namespace=("workspace", "ws-1", "facts"),
        subject="LangGraph checkpoint",
        content="Checkpoint 用于保存图状态",
        source_evidence_ids=["evidence-1"],
        confidence=0.9,
        importance=0.8,
        status=MemoryStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_local_memory_store_persists_across_runtime_instances(tmp_path) -> None:
    settings = _settings()
    first = _record()

    _saver, _ledger, memory, _evidence, engine = _build_durable_stores(
        settings, tmp_path
    )
    try:
        assert isinstance(memory, SqlAlchemyMemoryStore)
        await memory.put(first)
    finally:
        await engine.dispose()

    # a brand-new assembly over the same runs dir must read the record back
    _saver, _ledger, reopened, _evidence, engine = _build_durable_stores(
        settings, tmp_path
    )
    try:
        found = await reopened.get_many_by_ids([first.id])
        assert [record.id for record in found] == [first.id]
        assert found[0].content == "Checkpoint 用于保存图状态"
    finally:
        await engine.dispose()


def test_sqlite_schema_migrates_legacy_payload_only_memory_table(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    payload = json.dumps(
        {
            "id": "legacy-memory-1",
            "type": "fact",
            "status": "active",
            "importance": 0.7,
            "confidence": 0.9,
            "created_at": "2026-09-15T00:00:00+00:00",
            "expires_at": None,
        }
    )
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE memory_records (
            id INTEGER NOT NULL PRIMARY KEY,
            namespace_scope VARCHAR(32) NOT NULL,
            namespace_owner VARCHAR(128) NOT NULL,
            namespace_kind VARCHAR(64) NOT NULL,
            store_key VARCHAR(512) NOT NULL,
            payload JSON NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO memory_records "
        "(namespace_scope, namespace_owner, namespace_kind, store_key, payload, updated_at) "
        "VALUES ('workspace', 'ws-1', 'facts', 'k', ?, '2026-09-15')",
        (payload,),
    )
    connection.commit()
    connection.close()

    _ensure_sqlite_schema(database)

    connection = sqlite3.connect(database)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(memory_records)")
        }
        assert {
            "memory_id",
            "memory_type",
            "status",
            "importance",
            "confidence",
            "created_at",
            "expires_at",
        } <= columns
        row = connection.execute(
            "SELECT memory_id, memory_type, status, importance "
            "FROM memory_records WHERE store_key = 'k'"
        ).fetchone()
        assert row == ("legacy-memory-1", "fact", "active", 0.7)
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert "ix_memory_records_recall" in indexes
    finally:
        connection.close()
