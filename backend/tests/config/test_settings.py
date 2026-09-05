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
    for name in [key for key in os.environ if key.startswith(("DEEPTRACE_", "OPENAI_"))]:
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
    assert settings.context_max_results == 10
    assert settings.context_direct_threshold_chars == 8_000
    assert settings.context_chunk_chars == 1_000
    assert settings.context_chunk_overlap_chars == 100
    assert settings.context_similarity_threshold == 0.42
    assert settings.planner_timeout_seconds == 60
    assert settings.writer_timeout_seconds == 60
    assert settings.max_runtime_seconds is None
    assert settings.openai_max_tokens is None
    assert not hasattr(settings, "max_task_rounds")
    assert not hasattr(settings, "task_concurrency")
    assert not hasattr(settings, "query_loop_threshold")


def test_missing_embedding_model_directory_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path / "missing-bge-m3")

    with pytest.raises(RuntimeError, match="Embedding 模型目录不存在"):
        Settings.from_env()


def test_chunk_overlap_must_be_smaller_than_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_CONTEXT_CHUNK_CHARS", "100")
    monkeypatch.setenv("DEEPTRACE_CONTEXT_CHUNK_OVERLAP_CHARS", "100")

    with pytest.raises(RuntimeError, match="overlap"):
        Settings.from_env()


def test_cost_limit_requires_pricing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_MAX_COST_USD", "1.00")
    monkeypatch.delenv("DEEPTRACE_INPUT_COST_PER_MILLION", raising=False)
    monkeypatch.delenv("DEEPTRACE_OUTPUT_COST_PER_MILLION", raising=False)

    with pytest.raises(RuntimeError, match="模型单价"):
        Settings.from_env()


def test_deep_settings_are_bounded(monkeypatch, tmp_path):
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_DEEP_MAX_STEPS", "8")
    assert Settings.from_env().deep_max_steps == 8
    monkeypatch.setenv("DEEPTRACE_DEEP_MAX_STEPS", "0")
    with pytest.raises(RuntimeError, match="DEEP_MAX_STEPS"):
        Settings.from_env()
