"""BGE-M3 text embeddings with per-run query-vector caching."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

class CompressionRuntime:
    """Hold the local embedding model without persisting transient vectors."""

    def __init__(self, model_path: Path | str, batch_size: int = 8) -> None:
        path = Path(model_path)
        if not path.is_dir():
            raise ValueError(f"Embedding 模型目录不存在：{path}")
        if batch_size < 1:
            raise ValueError("batch_size 必须大于 0")
        self.model = SentenceTransformer(str(path))
        self.batch_size = batch_size
        self.query_vectors: dict[str, np.ndarray] = {}

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """批量生成已归一化向量，使点积等价于余弦相似度。"""
        if not texts:
            dimension = self.model.get_sentence_embedding_dimension() or 0
            return np.empty((0, dimension), dtype=np.float32)
        vectors = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def query_vector(self, query: str) -> np.ndarray:
        """Cache query vectors so repeated query filtering embeds only once."""
        key = query.strip()
        if not key:
            raise ValueError("query 不能为空")
        if key not in self.query_vectors:
            self.query_vectors[key] = self.embed([key])[0]
        return self.query_vectors[key]
