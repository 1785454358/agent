"""Local BGE-M3 embedding gateway with one lazy model per runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


class BgeM3EmbeddingGateway:
    def __init__(
        self,
        model_path: Path,
        *,
        batch_size: int = 8,
        model_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._model_path = Path(model_path)
        if not self._model_path.is_dir():
            raise RuntimeError(
                f"BGE-M3 model directory does not exist: {self._model_path}"
            )
        self._batch_size = batch_size
        self._model_factory = model_factory or self._load_sentence_transformer
        self._model: Any | None = None
        self._encode_lock = asyncio.Lock()

    @staticmethod
    def _load_sentence_transformer(path: str) -> Any:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(path, local_files_only=True)

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            self._model = self._model_factory(str(self._model_path))
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in vectors.tolist()]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        values = list(texts)
        if not values:
            return []
        async with self._encode_lock:
            return await asyncio.to_thread(self._encode_sync, values)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_documents([text])
        return vectors[0]
