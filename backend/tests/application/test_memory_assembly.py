from __future__ import annotations

from pathlib import Path

from deeptrace.application.assembly import _build_memory_retriever
from deeptrace.config import Settings
from deeptrace.harness.memory.retriever import SemanticMemoryRetriever
from deeptrace.harness.memory.store import InMemoryMemoryStore


def _settings(tmp_path: Path, *, retrieval: str) -> Settings:
    model_path = tmp_path / "bge-m3"
    model_path.mkdir(exist_ok=True)
    return Settings(
        openai_api_key="test",
        openai_base_url="https://example.com/v1",
        openai_model="model",
        tavily_api_key="test",
        memory_retrieval=retrieval,
        embedding_model_path=model_path,
        chroma_persist_path=tmp_path / "chroma",
    )


def test_local_runtime_assembles_persistent_semantic_memory(tmp_path) -> None:
    retriever = _build_memory_retriever(
        _settings(tmp_path, retrieval="semantic"),
        InMemoryMemoryStore(),
        runs_dir=tmp_path,
    )

    assert isinstance(retriever, SemanticMemoryRetriever)
    assert (tmp_path / "chroma").is_dir()


def test_lexical_memory_does_not_construct_chroma(tmp_path) -> None:
    retriever = _build_memory_retriever(
        _settings(tmp_path, retrieval="lexical"),
        InMemoryMemoryStore(),
        runs_dir=tmp_path,
    )

    assert retriever is None
    assert not (tmp_path / "chroma").exists()
