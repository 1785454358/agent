"""网页块和研究笔记的双查询语义召回。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from deeptrace.context.embeddings import CompressionRuntime
from deeptrace.models import DocumentChunk, ResearchNote


@dataclass(frozen=True, slots=True)
class ChunkSelection:
    """一次 chunk 召回结果以及可观测的 top-1 分数。"""

    chunks: list[DocumentChunk]
    is_relevant: bool
    top1_user_score: float
    top1_active_score: float
    top1_fused_score: float


def select_relevant_chunks(
    runtime: CompressionRuntime,
    chunks: Sequence[DocumentChunk],
    user_query: str,
    active_query: str,
    top_k: int = 6,
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
    ranked = np.argsort(-fused_scores, kind="stable")[: min(top_k, len(chunks))]
    selected_positions: set[int] = set()
    for position_value in ranked:
        position = int(position_value)
        selected_positions.add(position)
        current = chunks[position]
        for neighbor in (position - 1, position + 1):
            if 0 <= neighbor < len(chunks):
                candidate = chunks[neighbor]
                if (
                    candidate.doc_id == current.doc_id
                    and abs(candidate.index - current.index) == 1
                ):
                    selected_positions.add(neighbor)
    return ChunkSelection(
        [chunks[position] for position in sorted(selected_positions)],
        True,
        top1_user,
        top1_active,
        top1_fused,
    )


def is_repeated_query(
    runtime: CompressionRuntime,
    query: str,
    history: Sequence[str],
    threshold: float = 0.85,
) -> bool:
    """语义相似度严格超过阈值时，判定 Agent 正在重复搜索。"""
    if not history:
        return False
    query_vector = runtime.query_vector(query)
    history_matrix = np.stack([runtime.query_vector(item) for item in history])
    return float(np.max(history_matrix @ query_vector)) > threshold


def note_embedding_text(note: ResearchNote) -> str:
    """笔记检索固定同时嵌入标题、要点和证据细节。"""
    return "\n".join([note.title, *note.key_points, *note.evidence_snippets])


def retrieve_notes(
    runtime: CompressionRuntime,
    notes: Sequence[ResearchNote],
    user_query: str,
    active_query: str,
    top_k: int = 8,
) -> list[ResearchNote]:
    """笔记层同样使用双查询 max，避免新研究方向被早期笔记压制。"""
    if not notes:
        return []
    if top_k < 1:
        raise ValueError("top_k 必须大于 0")
    vectors = runtime.embed([note_embedding_text(note) for note in notes])
    user_scores = vectors @ runtime.query_vector(user_query)
    active_scores = vectors @ runtime.query_vector(active_query)
    fused_scores = np.maximum(user_scores, active_scores)
    indices = np.argsort(-fused_scores, kind="stable")[: min(top_k, len(notes))]
    return [notes[int(index)] for index in indices]
