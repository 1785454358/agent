"""BGE-M3 模型与单次研究运行的向量注册表。"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from deeptrace.models import DocumentChunk


class CompressionRuntime:
    """持有本地模型和向量缓存，numpy 向量不写入 Graph State。"""

    def __init__(self, model_path: Path | str, batch_size: int = 8) -> None:
        path = Path(model_path)
        if not path.is_dir():
            raise ValueError(f"Embedding 模型目录不存在：{path}")
        if batch_size < 1:
            raise ValueError("batch_size 必须大于 0")
        self.model = SentenceTransformer(str(path))
        self.tokenizer = self.model.tokenizer
        self.batch_size = batch_size
        self.chunk_vectors: dict[str, np.ndarray] = {}
        self.query_vectors: dict[str, np.ndarray] = {}

    def count_tokens(self, text: str) -> int:
        """按 BGE-M3 自身 tokenizer 统计本地语义处理量。"""
        encoded = self.tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_attention_mask=False,
            return_token_type_ids=False,
            return_length=True,
            verbose=False,
        )
        length = encoded.get("length", 0)
        return int(length[0] if isinstance(length, list) else length)

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

    def register_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        """只批量计算尚未登记的 chunk，支持同页新问题免费重排。"""
        missing = [
            chunk for chunk in chunks if chunk.chunk_id not in self.chunk_vectors
        ]
        if not missing:
            return
        vectors = self.embed([chunk.text for chunk in missing])
        self.chunk_vectors.update(
            {
                chunk.chunk_id: vector
                for chunk, vector in zip(missing, vectors, strict=True)
            }
        )

    def query_vector(self, query: str) -> np.ndarray:
        """缓存查询向量；相同查询在后续轮次无需重复计算。"""
        key = query.strip()
        if not key:
            raise ValueError("query 不能为空")
        if key not in self.query_vectors:
            self.query_vectors[key] = self.embed([key])[0]
        return self.query_vectors[key]
