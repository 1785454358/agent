import os
from pathlib import Path

import pytest

from deeptrace.config import Settings


def _set_required_environment(
    monkeypatch: pytest.MonkeyPatch, model_path: Path
) -> None:
    monkeypatch.setattr(
        "deeptrace.config.settings.load_dotenv", lambda *args, **kwargs: False
    )
    for name in [
        key for key in os.environ if key.startswith(("DEEPTRACE_", "OPENAI_"))
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "real-value-not-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "model")
    monkeypatch.setenv("TAVILY_API_KEY", "real-value-not-used")
    monkeypatch.setenv("DEEPTRACE_EMBEDDING_MODEL_PATH", str(model_path))


def test_basic_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_required_environment(monkeypatch, tmp_path)

    settings = Settings.from_env()

    assert settings.search_query_count == 3
    assert settings.max_search_results_per_query == 5
    assert settings.scraper_concurrency == 15
    assert settings.model_context_tokens == 256_000
    assert settings.context_safety_tokens == 4_096
    assert settings.planner_timeout_seconds == 60
    assert settings.writer_timeout_seconds == 60
    assert settings.openai_max_tokens is None
    assert settings.memory_retrieval == "semantic"
    assert settings.chroma_collection == "deeptrace-long-term-memory"
    assert settings.chroma_persist_path == Path("chroma")
    assert settings.memory_top_k == 5
    assert not hasattr(settings, "max_task_rounds")
    assert not hasattr(settings, "task_concurrency")
    assert not hasattr(settings, "query_loop_threshold")


def test_distributed_runtime_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_RUNTIME_MODE", "distributed")
    monkeypatch.setenv(
        "DEEPTRACE_MYSQL_DSN", "mysql+asyncmy://app:pw@mysql/deepresearch"
    )
    monkeypatch.setenv("DEEPTRACE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("DEEPTRACE_CHROMA_URL", "http://chroma:8000")
    monkeypatch.setenv("DEEPTRACE_WORKER_LEASE_SECONDS", "180")

    settings = Settings.from_env()

    assert settings.runtime_mode == "distributed"
    assert settings.mysql_dsn == "mysql+asyncmy://app:pw@mysql/deepresearch"
    assert settings.redis_url == "redis://redis:6379/0"
    assert settings.redis_job_stream == "deeptrace:research:jobs"
    assert settings.redis_consumer_group == "research-workers"
    assert settings.worker_lease_seconds == 180
    assert settings.worker_max_attempts == 3
    assert settings.chroma_url == "http://chroma:8000"


def test_invalid_runtime_mode_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_RUNTIME_MODE", "cluster")

    with pytest.raises(RuntimeError, match="DEEPTRACE_RUNTIME_MODE"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("missing_name", "present_name", "present_value"),
    [
        ("DEEPTRACE_MYSQL_DSN", "DEEPTRACE_REDIS_URL", "redis://redis:6379/0"),
        (
            "DEEPTRACE_REDIS_URL",
            "DEEPTRACE_MYSQL_DSN",
            "mysql+asyncmy://app:pw@mysql/deepresearch",
        ),
    ],
)
def test_distributed_mode_requires_both_connections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    missing_name: str,
    present_name: str,
    present_value: str,
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_RUNTIME_MODE", "distributed")
    monkeypatch.delenv(missing_name, raising=False)
    monkeypatch.setenv(present_name, present_value)

    with pytest.raises(RuntimeError, match=missing_name):
        Settings.from_env()


def test_lexical_mode_does_not_require_embedding_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path / "missing-bge-m3")
    monkeypatch.setenv("DEEPTRACE_MEMORY_RETRIEVAL", "lexical")

    assert Settings.from_env().memory_retrieval == "lexical"


def test_distributed_semantic_memory_requires_chroma_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_RUNTIME_MODE", "distributed")
    monkeypatch.setenv("DEEPTRACE_MYSQL_DSN", "mysql+asyncmy://app:pw@mysql/db")
    monkeypatch.setenv("DEEPTRACE_REDIS_URL", "redis://redis:6379/0")

    with pytest.raises(RuntimeError, match="DEEPTRACE_CHROMA_URL"):
        Settings.from_env()


def test_model_context_window_is_configurable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_MODEL_CONTEXT_TOKENS", "64000")
    monkeypatch.setenv("DEEPTRACE_CONTEXT_SAFETY_TOKENS", "1024")

    settings = Settings.from_env()

    assert settings.model_context_tokens == 64_000
    assert settings.context_safety_tokens == 1_024
