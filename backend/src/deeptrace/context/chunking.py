"""使用 BGE tokenizer 切分网页正文。"""

from __future__ import annotations

from deeptrace.context.embeddings import CompressionRuntime
from deeptrace.models import DocumentChunk, RawDocument


def chunk_document(
    runtime: CompressionRuntime,
    document: RawDocument,
    chunk_tokens: int = 800,
    overlap_tokens: int = 100,
) -> list[DocumentChunk]:
    """按默认 800/100 token 窗口切分，并保留原文字符位置。"""
    if chunk_tokens < 1:
        raise ValueError("chunk_tokens 必须大于 0")
    if not 0 <= overlap_tokens < chunk_tokens:
        raise ValueError("overlap_tokens 必须位于 [0, chunk_tokens) 区间")
    if not document.content:
        return []
    encoded = runtime.tokenizer(
        document.content,
        add_special_tokens=False,
        return_offsets_mapping=True,
        truncation=False,
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
            text = runtime.tokenizer.decode(
                token_ids[token_start:token_end], skip_special_tokens=True
            )
            char_start = max(document.content.find(text), 0)
            char_end = char_start + len(text)
        chunks.append(
            DocumentChunk(
                chunk_id=f"{document.doc_id}:{index}",
                doc_id=document.doc_id,
                index=index,
                text=text,
                token_count=token_end - token_start,
                char_start=char_start,
                char_end=char_end,
            )
        )
        if token_end == len(token_ids):
            break
    return chunks
