from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _config(database_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
    return config


def test_memory_migration_backfills_query_columns_without_editing_old_revision(
    tmp_path,
) -> None:
    database_path = tmp_path / "migration.db"
    config = _config(database_path)
    command.upgrade(config, "20260913_03")
    payload = {
        "id": "mem-existing",
        "type": "fact",
        "namespace": ["workspace", "ws-1", "facts"],
        "subject": "existing",
        "content": "existing content",
        "source_evidence_ids": ["evidence-1"],
        "confidence": 0.9,
        "status": "active",
        "created_at": "2026-09-13T00:00:00Z",
        "updated_at": "2026-09-13T00:00:00Z",
        "expires_at": None,
        "version": 1,
        "supersedes": None,
    }
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO memory_records "
            "(namespace_scope, namespace_owner, namespace_kind, store_key, payload, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "workspace",
                "ws-1",
                "facts",
                "existing|v1",
                json.dumps(payload),
                "2026-09-13 00:00:00",
            ),
        )
        connection.commit()

    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(memory_records)")
        }
        row = connection.execute(
            "SELECT memory_id, memory_type, status, importance, confidence "
            "FROM memory_records WHERE store_key = 'existing|v1'"
        ).fetchone()
    assert {
        "memory_id",
        "memory_type",
        "status",
        "importance",
        "confidence",
        "created_at",
        "expires_at",
    } <= columns
    assert row == ("mem-existing", "fact", "active", 0.5, 0.9)
