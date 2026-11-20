"""Local schema initialization and compatibility migrations."""

from pathlib import Path


def ensure_sqlite_schema(db_path: Path) -> None:
    """Create/migrate the local SQLite schema synchronously.

    Order matters for databases created by earlier builds:
    1. create tables (IF NOT EXISTS),
    2. add missing columns and backfill them,
    3. only then create indexes (they reference the new columns).
    """
    import hashlib
    import json
    import sqlite3

    from sqlalchemy import create_engine
    from sqlalchemy.schema import CreateIndex, CreateTable

    from deeptrace.persistence.orm import (
        CheckpointRow,
        CheckpointWriteRow,
        EvidenceRecordRow,
        MemoryRecordRow,
        ModelBudgetRow,
        ThreadLeaseRow,
        ToolExecutionRow,
    )

    sync_engine = create_engine("sqlite://")
    table_statements = [
        str(CreateTable(table).compile(sync_engine))
        for table in (
            CheckpointRow.__table__,
            CheckpointWriteRow.__table__,
            EvidenceRecordRow.__table__,
            MemoryRecordRow.__table__,
            ThreadLeaseRow.__table__,
            ToolExecutionRow.__table__,
            ModelBudgetRow.__table__,
        )
    ]
    index_statements = [
        str(CreateIndex(index).compile(sync_engine))
        for table in (
            CheckpointRow.__table__,
            CheckpointWriteRow.__table__,
            EvidenceRecordRow.__table__,
            MemoryRecordRow.__table__,
            ToolExecutionRow.__table__,
        )
        for index in table.indexes
    ]

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "PRAGMA table_info(evidence_records)"
        )  # ensure the file exists before CREATE IF NOT EXISTS runs
        for statement in table_statements:
            connection.execute(
                statement.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS")
            )

        def _columns(table: str) -> set[str]:
            return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}

        # column migration + backfill BEFORE the version index exists
        evidence_columns = _columns("evidence_records")
        connection.create_function(
            "deeptrace_sha256_hex",
            1,
            lambda value: hashlib.sha256((value or "").encode("utf-8")).hexdigest(),
        )
        if "canonical_url_hash" not in evidence_columns:
            connection.execute(
                "ALTER TABLE evidence_records ADD COLUMN canonical_url_hash VARCHAR(64)"
            )
            connection.execute(
                "UPDATE evidence_records "
                "SET canonical_url_hash = deeptrace_sha256_hex(canonical_url)"
            )
        elif connection.execute(
            "SELECT COUNT(*) FROM evidence_records "
            "WHERE canonical_url_hash IS NULL OR canonical_url_hash = ''"
        ).fetchone()[0]:
            connection.execute(
                "UPDATE evidence_records "
                "SET canonical_url_hash = deeptrace_sha256_hex(canonical_url) "
                "WHERE canonical_url_hash IS NULL OR canonical_url_hash = ''"
            )

        # Older local databases shipped a payload-only memory_records table.
        # Add the authoritative query columns and backfill them from payload
        # before the recall index (which references memory_type) is created.
        memory_columns = _columns("memory_records")
        memory_required = {
            "memory_id": "VARCHAR(128)",
            "memory_type": "VARCHAR(32)",
            "status": "VARCHAR(32)",
            "importance": "FLOAT",
            "confidence": "FLOAT",
            "created_at": "DATETIME",
            "expires_at": "DATETIME",
        }
        if any(name not in memory_columns for name in memory_required):

            def _memory_field(payload: str | None, key: str) -> object:
                if not payload:
                    return None
                try:
                    data = json.loads(payload) if isinstance(payload, str) else payload
                except (TypeError, ValueError):
                    return None
                if not isinstance(data, dict):
                    return None
                value = data.get(key)
                return value if isinstance(value, (str, int, float)) else None

            for name, ddl in memory_required.items():
                if name not in memory_columns:
                    connection.execute(
                        f"ALTER TABLE memory_records ADD COLUMN {name} {ddl}"
                    )
            connection.create_function("deeptrace_memory_field", 2, _memory_field)
            connection.execute(
                "UPDATE memory_records SET "
                "memory_id = COALESCE(memory_id, deeptrace_memory_field(payload, 'id')), "
                "memory_type = COALESCE(memory_type, deeptrace_memory_field(payload, 'type')), "
                "status = COALESCE(status, deeptrace_memory_field(payload, 'status')), "
                "importance = COALESCE(importance, deeptrace_memory_field(payload, 'importance')), "
                "confidence = COALESCE(confidence, deeptrace_memory_field(payload, 'confidence')), "
                "created_at = COALESCE(created_at, deeptrace_memory_field(payload, 'created_at')), "
                "expires_at = COALESCE(expires_at, deeptrace_memory_field(payload, 'expires_at'))"
            )

        # Older local databases predate the tool ledger's mode/caller identity
        # and per-call consumption columns. Add them before the ledger query
        # runs, otherwise every tool call fails with "no such column".
        tool_columns = _columns("tool_executions")
        tool_required = {
            "mode": "VARCHAR(32)",
            "caller_id": "VARCHAR(128)",
            "consumed_tool_calls": "INTEGER DEFAULT 0",
            "consumed_network_requests": "INTEGER DEFAULT 0",
            "consumed_fetched_pages": "INTEGER DEFAULT 0",
        }
        for name, ddl in tool_required.items():
            if name not in tool_columns:
                connection.execute(
                    f"ALTER TABLE tool_executions ADD COLUMN {name} {ddl}"
                )

        for statement in index_statements:
            connection.execute(
                statement.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS").replace(
                    "CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS"
                )
            )
        connection.commit()
    finally:
        connection.close()
