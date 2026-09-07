from pathlib import Path

import yaml


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


def test_compose_declares_required_services_and_health_dependencies() -> None:
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )

    assert set(compose["services"]) == {"mysql", "redis", "api", "worker"}
    api = compose["services"]["api"]
    worker = compose["services"]["worker"]
    assert api["environment"]["DEEPTRACE_RUNTIME_MODE"] == "distributed"
    assert api["depends_on"]["mysql"]["condition"] == "service_healthy"
    assert api["depends_on"]["redis"]["condition"] == "service_healthy"
    assert worker["depends_on"]["api"]["condition"] == "service_healthy"
    assert worker["command"] == ["python", "-m", "deeptrace.worker"]
    assert "ports" not in compose["services"]["mysql"]
    assert "ports" not in compose["services"]["redis"]
    assert any(volume.endswith(":/models/bge-m3:ro") for volume in api["volumes"])
    assert any(volume.endswith(":/models/bge-m3:ro") for volume in worker["volumes"])


def test_migration_contains_runtime_tables_and_indexes() -> None:
    migration = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20260907_01_create_research_runtime.py"
    ).read_text(encoding="utf-8")

    assert 'op.create_table("research_runs"' in migration
    assert 'op.create_table("run_events"' in migration
    assert 'op.create_index("ix_research_runs_created_at"' in migration
    assert 'op.create_index("ix_run_events_run_id_id"' in migration


def test_dockerfile_installs_locked_project_and_runs_as_non_root() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "playwright install --with-deps chromium" in dockerfile
    assert "USER app" in dockerfile
