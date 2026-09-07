import os
from pathlib import Path

import pytest

from deeptrace.config import Settings


def set_required(monkeypatch: pytest.MonkeyPatch, model_path: Path) -> None:
    monkeypatch.setattr(
        "deeptrace.config.settings.load_dotenv", lambda *args, **kwargs: False
    )
    for key in list(os.environ):
        if key.startswith(("DEEPTRACE_", "OPENAI_")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "model")
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    monkeypatch.setenv("DEEPTRACE_EMBEDDING_MODEL_PATH", str(model_path))


def test_multi_agent_settings_have_independent_defaults(monkeypatch, tmp_path):
    set_required(monkeypatch, tmp_path)
    settings = Settings.from_env()
    assert settings.multi_agent_max_researchers == 6
    assert settings.multi_agent_max_batch_size == 3
    assert settings.multi_agent_concurrency == 3
    assert settings.multi_agent_max_supervisor_rounds == 3
    assert settings.multi_agent_max_researcher_rounds == 3
    assert settings.multi_agent_max_tool_calls == 30
    assert settings.multi_agent_max_tools_per_researcher == 10
    assert settings.multi_agent_memory_path == Path("memory/multi-agent-pages.jsonl")


def test_multi_agent_memory_must_not_share_legacy_path(monkeypatch, tmp_path):
    set_required(monkeypatch, tmp_path)
    same = tmp_path / "pages.jsonl"
    monkeypatch.setenv("DEEPTRACE_MEMORY_PATH", str(same))
    monkeypatch.setenv("DEEPTRACE_MULTI_AGENT_MEMORY_PATH", str(same))
    with pytest.raises(RuntimeError, match="MEMORY_PATH"):
        Settings.from_env()


def test_multi_agent_concurrency_cannot_exceed_batch_size(monkeypatch, tmp_path):
    set_required(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_MULTI_AGENT_MAX_BATCH_SIZE", "2")
    monkeypatch.setenv("DEEPTRACE_MULTI_AGENT_CONCURRENCY", "3")
    with pytest.raises(RuntimeError, match="CONCURRENCY"):
        Settings.from_env()


def test_multi_agent_requires_dispatch_and_final_supervisor_rounds(
    monkeypatch, tmp_path
):
    set_required(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_MULTI_AGENT_MAX_SUPERVISOR_ROUNDS", "1")
    with pytest.raises(RuntimeError, match="MAX_SUPERVISOR_ROUNDS"):
        Settings.from_env()
