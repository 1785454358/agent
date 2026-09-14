from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from deeptrace.harness.memory.embedding import BgeM3EmbeddingGateway


class _FakeSentenceTransformer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int, bool]] = []

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> np.ndarray:
        self.calls.append((texts, batch_size, normalize_embeddings))
        return np.asarray([[float(len(text)), 1.0] for text in texts], dtype=np.float32)


def test_bge_gateway_rejects_a_missing_local_model(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="BGE-M3 model directory does not exist"):
        BgeM3EmbeddingGateway(tmp_path / "missing")


@pytest.mark.asyncio
async def test_bge_gateway_loads_once_and_returns_plain_float_vectors(tmp_path) -> None:
    model = _FakeSentenceTransformer()
    loads: list[Path] = []

    def load(path: str) -> _FakeSentenceTransformer:
        loads.append(Path(path))
        return model

    gateway = BgeM3EmbeddingGateway(tmp_path, batch_size=4, model_factory=load)

    documents = await gateway.embed_documents(["alpha", "beta"])
    query = await gateway.embed_query("gamma")

    assert loads == [tmp_path]
    assert documents == [[5.0, 1.0], [4.0, 1.0]]
    assert query == [5.0, 1.0]
    assert model.calls == [(["alpha", "beta"], 4, True), (["gamma"], 4, True)]
