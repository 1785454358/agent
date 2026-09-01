"""网页上下文分块、向量检索与压缩公共接口。"""

from deeptrace.context.chunking import chunk_document
from deeptrace.context.compression import (
    CompressionRequest,
    CompressionService,
    ResearchNotePayload,
    build_extractive_note,
    parse_note_json,
)
from deeptrace.context.embeddings import CompressionRuntime
from deeptrace.context.retrieval import (
    ChunkSelection,
    is_repeated_query,
    note_embedding_text,
    retrieve_notes,
    select_relevant_chunks,
)
from deeptrace.context.temporal import normalize_temporal_relation

__all__ = [
    "ChunkSelection",
    "CompressionRequest",
    "CompressionRuntime",
    "CompressionService",
    "ResearchNotePayload",
    "build_extractive_note",
    "chunk_document",
    "is_repeated_query",
    "note_embedding_text",
    "parse_note_json",
    "retrieve_notes",
    "select_relevant_chunks",
    "normalize_temporal_relation",
]
