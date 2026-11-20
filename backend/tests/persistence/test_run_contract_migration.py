import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_existing_run_keeps_detail_and_gets_unknown_sufficiency(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPTRACE_MYSQL_DSN", raising=False)
    path = tmp_path / "runs.db"
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path.as_posix()}")
    command.upgrade(config, "20261010_01")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO research_runs (id, question, mode, status, created_at, termination_reason, "
            "answer, sources, search_queries, unresolved_gaps, request_payload, attempt_count, version, thread_id) "
            "VALUES (?, ?, ?, ?, ?, ?, '', '[]', '[]', '[]', '{}', 0, 0, '')",
            ("old", "Question", "workflow", "completed", "2026-11-08", "workflow_completed"),
        )
    command.upgrade(config, "head")
    with sqlite3.connect(path) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not {"trace_spans", "trace_events"} & names
        assert connection.execute(
            "SELECT termination_reason, research_sufficiency FROM research_runs WHERE id = 'old'"
        ).fetchone() == ("workflow_completed", "unknown")
    command.downgrade(config, "20261010_01")
    command.upgrade(config, "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT research_sufficiency FROM research_runs").fetchone() == ("unknown",)
