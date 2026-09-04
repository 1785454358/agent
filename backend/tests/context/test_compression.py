import asyncio

import numpy as np

from deeptrace import context as context_module


class SpyEmbeddingRuntime:
    def __init__(self) -> None:
        self.embed_calls = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        self.embed_calls += 1
        return np.ones((len(texts), 1), dtype=np.float32)

    def query_vector(self, query: str) -> np.ndarray:
        self.embed_calls += 1
        return np.ones(1, dtype=np.float32)


class DeterministicEmbeddingRuntime:
    """Only chunks containing the literal marker are relevant to the query."""

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            [[1.0, 0.0] if "相关标记" in text else [0.0, 1.0] for text in texts],
            dtype=np.float32,
        )

    def query_vector(self, query: str) -> np.ndarray:
        return np.asarray([1.0, 0.0], dtype=np.float32)


class RankedEmbeddingRuntime:
    """Give later chunks higher scores so selection order differs from reading order."""

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            [[0.43 + index * 0.01, 0.0] for index in range(len(texts))],
            dtype=np.float32,
        )

    def query_vector(self, query: str) -> np.ndarray:
        return np.asarray([1.0, 0.0], dtype=np.float32)


def test_small_context_skips_embedding(raw_document) -> None:
    runtime = SpyEmbeddingRuntime()
    compressor = context_module.ContextCompressor(runtime, direct_threshold_chars=8000)

    context = asyncio.run(compressor.aget_context("问题", [raw_document]))

    assert runtime.embed_calls == 0
    assert context == (
        "Source: https://example.com/a\n"
        "Title: 来源标题\n"
        "Content: 整页正文唯一标记\n"
    )


def test_small_documents_over_hard_limit_use_embeddings_so_later_source_can_win(
    raw_document,
) -> None:
    documents = [
        raw_document.model_copy(
            update={
                "doc_id": f"doc-{index:02d}",
                "final_url": f"https://example.com/{index}",
                "title": f"来源 {index}",
                "content": "普通内容",
            }
        )
        for index in range(10)
    ]
    relevant = raw_document.model_copy(
        update={
            "doc_id": "doc-10",
            "final_url": "https://example.com/relevant",
            "title": "相关来源",
            "content": "相关标记",
        }
    )
    documents.append(relevant)
    compressor = context_module.ContextCompressor(
        DeterministicEmbeddingRuntime(), direct_threshold_chars=8000
    )

    context = asyncio.run(compressor.aget_context("相关", documents, max_results=99))

    assert context == (
        "Source: https://example.com/relevant\n"
        "Title: 相关来源\n"
        "Content: 相关标记\n"
    )


def test_large_context_filters_character_chunks(raw_document) -> None:
    content = "相关标记" + "甲" * 996 + "乙" * 2200
    document = raw_document.model_copy(update={"content": content})
    compressor = context_module.ContextCompressor(
        DeterministicEmbeddingRuntime(),
        direct_threshold_chars=10,
        chunk_size=1000,
        chunk_overlap=100,
        similarity_threshold=0.42,
    )

    context = asyncio.run(compressor.aget_context("相关", [document], max_results=10))

    assert context == context_module.format_document_context(document, content[:1000])
    assert "乙" not in context


def test_large_context_caps_results_and_restores_reading_order(raw_document) -> None:
    content = "".join(chr(0x4E00 + index) * 900 for index in range(13))
    document = raw_document.model_copy(update={"content": content})
    compressor = context_module.ContextCompressor(
        RankedEmbeddingRuntime(),
        direct_threshold_chars=10,
        chunk_size=1000,
        chunk_overlap=100,
        similarity_threshold=0.42,
    )

    context = asyncio.run(compressor.aget_context("问题", [document], max_results=99))
    contents = [
        block.split("\n", 2)[2].removeprefix("Content: ").rstrip()
        for block in context.split("Source: ")[1:]
    ]

    assert len(contents) == 10
    positions = [document.content.index(item) for item in contents]
    assert positions == sorted(positions)


def test_empty_documents_produce_empty_context(raw_document) -> None:
    empty = raw_document.model_copy(update={"content": "  "})
    compressor = context_module.ContextCompressor(SpyEmbeddingRuntime())

    context = asyncio.run(compressor.aget_context("问题", [empty]))

    assert context == ""
