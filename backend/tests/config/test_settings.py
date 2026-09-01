from pathlib import Path

import pytest

from deeptrace.config import Settings


def _set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "real-value-not-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "model")
    monkeypatch.setenv("TAVILY_API_KEY", "real-value-not-used")


def test_stage_two_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_environment(monkeypatch)

    settings = Settings.from_env()

    assert settings.embedding_model_path == Path(r"D:\Dev\Models\bge-m3")
    assert settings.min_relevance_score == 0.45
    assert settings.embedding_batch_size == 8
    assert settings.compression_concurrency == 3
    assert settings.soft_max_steps == 8
    assert settings.hard_max_steps == 12
    assert settings.query_loop_threshold == 0.85
    assert settings.token_encoding == "cl100k_base"


def test_missing_embedding_model_directory_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch)
    missing_path = tmp_path / "missing-bge-m3"
    monkeypatch.setenv("DEEPTRACE_EMBEDDING_MODEL_PATH", str(missing_path))

    with pytest.raises(RuntimeError, match="Embedding 模型目录不存在"):
        Settings.from_env()


def test_soft_step_limit_cannot_exceed_hard_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("DEEPTRACE_SOFT_MAX_STEPS", "13")
    monkeypatch.setenv("DEEPTRACE_HARD_MAX_STEPS", "12")

    with pytest.raises(RuntimeError, match="soft_max_steps"):
        Settings.from_env()


def test_stage3_budget_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("DEEPTRACE_EMBEDDING_MODEL_PATH", str(tmp_path))

    settings = Settings.from_env()

    assert settings.max_research_tasks == 4
    assert settings.max_task_rounds == 3
    assert settings.min_sources_per_task == 2
    assert settings.max_fetched_pages == 20
    assert settings.max_runtime_seconds == 600
    assert settings.max_api_tokens == 120_000


def test_cost_limit_requires_pricing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("DEEPTRACE_EMBEDDING_MODEL_PATH", str(tmp_path))
    monkeypatch.setenv("DEEPTRACE_MAX_COST_USD", "1.00")

    with pytest.raises(RuntimeError, match="模型单价"):
        Settings.from_env()
