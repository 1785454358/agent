"""BGE-M3 分块、向量注册和双查询语义召回。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from deeptrace.models import DocumentChunk, RawDocument


@dataclass(frozen=True, slots=True)
class ChunkSelection:
    """一次 chunk 召回结果以及可观测的 top-1 分数。"""
    chunks: list[DocumentChunk]
    is_relevant: bool
    top1_user_score: float
    top1_active_score: float
    top1_fused_score: float


class CompressionRuntime:
    """单次研究运行持有的本地模型和向量缓存。

    numpy 向量只存在这里，不写入 LangGraph State，避免 checkpoint 膨胀。
    """
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
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """批量生成已归一化向量，使点积等价于余弦相似度。"""
        if not texts:
            dimension = self.model.get_sentence_embedding_dimension() or 0
            return np.empty((0, dimension), dtype=np.float32)
        vectors = self.model.encode(
            list(texts), batch_size=self.batch_size, convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def register_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        """只批量计算尚未登记的 chunk，支持同页新问题免费重排。"""
        missing = [chunk for chunk in chunks if chunk.chunk_id not in self.chunk_vectors]
        if not missing:
            return
        vectors = self.embed([chunk.text for chunk in missing])
        self.chunk_vectors.update(
            {chunk.chunk_id: vector for chunk, vector in zip(missing, vectors, strict=True)}
        )

    def query_vector(self, query: str) -> np.ndarray:
        """缓存查询向量；相同查询在后续轮次无需重复计算。"""
        key = query.strip()
        if not key:
            raise ValueError("query 不能为空")
        if key not in self.query_vectors:
            self.query_vectors[key] = self.embed([key])[0]
        return self.query_vectors[key]


def chunk_document(
    runtime: CompressionRuntime, document: RawDocument,
    chunk_tokens: int = 800, overlap_tokens: int = 100,
) -> list[DocumentChunk]:
    """使用 BGE tokenizer 按 800/100 默认窗口切分，并保留原文字符位置。"""
    if chunk_tokens < 1:
        raise ValueError("chunk_tokens 必须大于 0")
    if not 0 <= overlap_tokens < chunk_tokens:
        raise ValueError("overlap_tokens 必须位于 [0, chunk_tokens) 区间")
    if not document.content:
        return []
    encoded = runtime.tokenizer(
        document.content, add_special_tokens=False,
        return_offsets_mapping=True, truncation=False,
    )
    token_ids = encoded["input_ids"]
    offsets = encoded.get("offset_mapping")
    step = chunk_tokens - overlap_tokens
    chunks: list[DocumentChunk] = []
    for index, token_start in enumerate(range(0, len(token_ids), step)):
        token_end = min(token_start + chunk_tokens, len(token_ids))
        if offsets:
            char_start = int(offsets[token_start][0])
            char_end = int(offsets[token_end - 1][1])
            text = document.content[char_start:char_end]
        else:
            text = runtime.tokenizer.decode(token_ids[token_start:token_end], skip_special_tokens=True)
            char_start = max(document.content.find(text), 0)
            char_end = char_start + len(text)
        chunks.append(DocumentChunk(
            chunk_id=f"{document.doc_id}:{index}", doc_id=document.doc_id,
            index=index, text=text, token_count=token_end - token_start,
            char_start=char_start, char_end=char_end,
        ))
        if token_end == len(token_ids):
            break
    return chunks


def select_relevant_chunks(
    runtime: CompressionRuntime, chunks: Sequence[DocumentChunk],
    user_query: str, active_query: str, top_k: int = 6,
    threshold: float = 0.45,
) -> ChunkSelection:
    """按双查询最大值宽召回，命中后补充每个块的相邻上下文。"""
    if not chunks:
        return ChunkSelection([], False, -1.0, -1.0, -1.0)
    if top_k < 1:
        raise ValueError("top_k 必须大于 0")
    runtime.register_chunks(chunks)
    matrix = np.stack([runtime.chunk_vectors[chunk.chunk_id] for chunk in chunks])
    user_scores = matrix @ runtime.query_vector(user_query)
    active_scores = matrix @ runtime.query_vector(active_query)
    fused_scores = np.maximum(user_scores, active_scores)
    top1_user = float(np.max(user_scores))
    top1_active = float(np.max(active_scores))
    top1_fused = float(np.max(fused_scores))
    if top1_fused < threshold:
        return ChunkSelection([], False, top1_user, top1_active, top1_fused)
    ranked = np.argsort(-fused_scores, kind="stable")[:min(top_k, len(chunks))]
    selected_positions: set[int] = set()
    for position_value in ranked:
        position = int(position_value)
        selected_positions.add(position)
        current = chunks[position]
        for neighbor in (position - 1, position + 1):
            if 0 <= neighbor < len(chunks):
                candidate = chunks[neighbor]
                if candidate.doc_id == current.doc_id and abs(candidate.index - current.index) == 1:
                    selected_positions.add(neighbor)
    return ChunkSelection(
        [chunks[position] for position in sorted(selected_positions)],
        True, top1_user, top1_active, top1_fused,
    )


def is_repeated_query(
    runtime: CompressionRuntime, query: str, history: Sequence[str],
    threshold: float = 0.85,
) -> bool:
    """语义相似度严格超过阈值时，判定 Agent 正在重复搜索。"""
    if not history:
        return False
    query_vector = runtime.query_vector(query)
    history_matrix = np.stack([runtime.query_vector(item) for item in history])
    return float(np.max(history_matrix @ query_vector)) > threshold
