"""相关块压缩为 ResearchNote，并提供可恢复的失败路径。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Sequence

import json_repair
import numpy as np
from pydantic import BaseModel, Field, ValidationError

from deeptrace.embedding import ChunkSelection, CompressionRuntime
from deeptrace.models import CompressionOutcome, RawDocument, ResearchNote, TokenUsage
from deeptrace.prompts.compression import build_compression_messages


class ResearchNotePayload(BaseModel):
    """压缩模型必须返回的最小结构，不接受空笔记。"""
    title: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    evidence_snippets: list[str] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class CompressionRequest:
    """一项可独立并发执行的网页压缩请求。"""
    tool_call_id: str
    order: int
    document: RawDocument
    selection: ChunkSelection
    active_query: str


def parse_note_json(raw: str) -> ResearchNotePayload:
    """先严格校验，再修复常见 JSON 格式问题并重新校验。"""
    try:
        return ResearchNotePayload.model_validate_json(raw)
    except (ValidationError, ValueError, json.JSONDecodeError):
        try:
            repaired = json_repair.loads(raw)
            return ResearchNotePayload.model_validate(repaired)
        except (ValidationError, ValueError, TypeError) as exc:
            raise ValueError("无法解析 ResearchNote JSON") from exc


def _note_id(doc_id: str, active_query: str) -> str:
    digest = hashlib.sha256(f"{doc_id}\0{active_query}".encode("utf-8")).hexdigest()
    return f"note-{digest[:20]}"


def build_extractive_note(
    document: RawDocument,
    selection: ChunkSelection,
    active_query: str,
    error: str,
) -> ResearchNote:
    """压缩最终失败时直接保留全部入选块，保证已抓信息不丢失。"""
    snippets = [chunk.text for chunk in selection.chunks if chunk.text.strip()]
    return ResearchNote(
        note_id=_note_id(document.doc_id, active_query),
        doc_id=document.doc_id,
        active_query=active_query,
        title=document.title or document.final_url,
        key_points=snippets[:3] or ["未提取到相关正文"],
        evidence_snippets=snippets or ["未提取到相关正文"],
        source_url=document.final_url,
        relevance_score=selection.top1_fused_score,
        compression_status="extractive_fallback",
        error=error,
    )


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
    indices = np.argsort(-fused_scores, kind="stable")[:min(top_k, len(notes))]
    return [notes[int(index)] for index in indices]


class CompressionService:
    """有界并发调用 LLM；单页失败不会取消同批其他页面。"""

    def __init__(self, model: Any, concurrency: int = 3) -> None:
        if concurrency < 1:
            raise ValueError("concurrency 必须大于 0")
        self._model = model
        self._semaphore = asyncio.Semaphore(concurrency)

    @staticmethod
    def _messages(request: CompressionRequest) -> list[Any]:
        return build_compression_messages(
            active_query=request.active_query,
            title=request.document.title,
            url=request.document.final_url,
            chunks=[
                (chunk.index, chunk.text) for chunk in request.selection.chunks
            ],
        )

    @staticmethod
    def _message_text(message: Any) -> str:
        content = getattr(message, "content", message)
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    @staticmethod
    def _usage(message: Any) -> TokenUsage:
        metadata = getattr(message, "usage_metadata", None) or {}
        input_tokens = int(metadata.get("input_tokens", 0) or 0)
        output_tokens = int(metadata.get("output_tokens", 0) or 0)
        total_tokens = int(
            metadata.get("total_tokens", input_tokens + output_tokens)
            or input_tokens + output_tokens
        )
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _irrelevant_outcome(request: CompressionRequest) -> CompressionOutcome:
        note = ResearchNote(
            note_id=_note_id(request.document.doc_id, request.active_query),
            doc_id=request.document.doc_id,
            active_query=request.active_query,
            title=request.document.title or request.document.final_url,
            key_points=[],
            evidence_snippets=[],
            source_url=request.document.final_url,
            relevance_score=request.selection.top1_fused_score,
            compression_status="irrelevant",
        )
        return CompressionOutcome(
            tool_call_id=request.tool_call_id, note=note, order=request.order
        )

    async def compress_one(self, request: CompressionRequest) -> CompressionOutcome:
        """JSON repair 后仍失败会重试一次，最终回退为抽取式笔记。"""
        if not request.selection.is_relevant:
            return self._irrelevant_outcome(request)
        messages = self._messages(request)
        last_error = "compression_failed"
        total_usage = TokenUsage()
        async with self._semaphore:
            for _attempt in range(2):
                try:
                    response = await self._model.ainvoke(messages)
                    usage = self._usage(response)
                    total_usage = TokenUsage(
                        input_tokens=total_usage.input_tokens + usage.input_tokens,
                        output_tokens=total_usage.output_tokens + usage.output_tokens,
                        total_tokens=total_usage.total_tokens + usage.total_tokens,
                    )
                    payload = parse_note_json(self._message_text(response))
                    note = ResearchNote(
                        note_id=_note_id(request.document.doc_id, request.active_query),
                        doc_id=request.document.doc_id,
                        active_query=request.active_query,
                        title=payload.title,
                        key_points=payload.key_points,
                        evidence_snippets=payload.evidence_snippets,
                        source_url=request.document.final_url,
                        relevance_score=request.selection.top1_fused_score,
                        compression_status="compressed",
                    )
                    return CompressionOutcome(
                        tool_call_id=request.tool_call_id,
                        note=note,
                        order=request.order,
                        usage=total_usage,
                    )
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
        return CompressionOutcome(
            tool_call_id=request.tool_call_id,
            note=build_extractive_note(
                request.document, request.selection, request.active_query, last_error
            ),
            error=last_error,
            order=request.order,
            usage=total_usage,
        )

    async def compress_many(
        self, requests: Sequence[CompressionRequest]
    ) -> list[CompressionOutcome]:
        """fan-out/fan-in 压缩，并按原始工具调用顺序恢复结果。"""
        results = await asyncio.gather(
            *(self.compress_one(request) for request in requests),
            return_exceptions=True,
        )
        outcomes: list[CompressionOutcome] = []
        for request, result in zip(requests, results, strict=True):
            if isinstance(result, BaseException):
                error = f"{type(result).__name__}: {result}"
                result = CompressionOutcome(
                    tool_call_id=request.tool_call_id,
                    note=build_extractive_note(
                        request.document, request.selection, request.active_query, error
                    ),
                    error=error,
                    order=request.order,
                )
            outcomes.append(result)
        return sorted(outcomes, key=lambda item: item.order)
