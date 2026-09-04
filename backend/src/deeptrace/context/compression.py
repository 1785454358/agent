"""Build Writer-ready research context directly from fetched documents."""

from __future__ import annotations

import asyncio
from typing import Sequence

from deeptrace.context.embeddings import CompressionRuntime
from deeptrace.models import RawDocument

_MAX_CONTEXT_RESULTS = 10


def format_document_context(document: RawDocument, content: str) -> str:
    """Format source text for direct consumption by the report Writer."""
    return (
        f"Source: {document.final_url}\n"
        f"Title: {document.title or document.final_url}\n"
        f"Content: {content.strip()}\n"
    )


def _split_text(text: str, size: int = 1000, overlap: int = 100) -> list[str]:
    """Split text by character offsets without creating persisted chunk objects."""
    if size < 1:
        raise ValueError("size 必须大于 0")
    if not 0 <= overlap < size:
        raise ValueError("overlap 必须位于 [0, size) 区间")
    if not text:
        return []

    step = size - overlap
    chunks: list[str] = []
    for start in range(0, len(text), step):
        chunk = text[start : start + size]
        if chunk:
            chunks.append(chunk)
        if start + size >= len(text):
            break
    return chunks


class ContextCompressor:
    """Select relevant source text and return one flat context string."""

    def __init__(
        self,
        runtime: CompressionRuntime,
        *,
        direct_threshold_chars: int = 8000,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        similarity_threshold: float = 0.42,
    ) -> None:
        if direct_threshold_chars < 0:
            raise ValueError("direct_threshold_chars 不能小于 0")
        if chunk_size < 1:
            raise ValueError("chunk_size 必须大于 0")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk_overlap 必须位于 [0, chunk_size) 区间")
        if not -1.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold 必须位于 [-1, 1]")
        self._runtime = runtime
        self._direct_threshold_chars = direct_threshold_chars
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._similarity_threshold = similarity_threshold

    def _filter_chunks(
        self,
        query: str,
        documents: Sequence[RawDocument],
        limit: int,
    ) -> str:
        candidates: list[tuple[RawDocument, str, int]] = []
        for document in documents:
            for text in _split_text(
                document.content.strip(),
                size=self._chunk_size,
                overlap=self._chunk_overlap,
            ):
                candidates.append((document, text, len(candidates)))
        if not candidates:
            return ""

        vectors = self._runtime.embed([text for _document, text, _order in candidates])
        scores = vectors @ self._runtime.query_vector(query)
        ranked_indices = sorted(
            (
                index
                for index in range(len(candidates))
                if float(scores[index]) >= self._similarity_threshold
            ),
            key=lambda index: (-float(scores[index]), candidates[index][2]),
        )[:limit]
        selected = sorted(
            (candidates[index] for index in ranked_indices), key=lambda item: item[2]
        )
        return "\n".join(
            format_document_context(document, text)
            for document, text, _order in selected
        )

    async def aget_context(
        self,
        query: str,
        documents: Sequence[RawDocument],
        max_results: int = _MAX_CONTEXT_RESULTS,
    ) -> str:
        """Return complete small documents or embedding-filtered large chunks."""
        if max_results < 1:
            return ""
        valid_documents = [
            document for document in documents if document.content.strip()
        ]
        if not valid_documents:
            return ""

        limit = min(max_results, _MAX_CONTEXT_RESULTS)
        total_chars = sum(len(document.content.strip()) for document in valid_documents)
        if (
            total_chars < self._direct_threshold_chars
            and len(valid_documents) <= max_results
        ):
            return "\n".join(
                format_document_context(document, document.content)
                for document in valid_documents[:limit]
            )

        return await asyncio.to_thread(
            self._filter_chunks,
            query,
            valid_documents,
            limit,
        )
