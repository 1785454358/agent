"""相关块压缩为 ResearchNote，并提供可恢复的失败路径。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date
from dataclasses import dataclass
from typing import Any, Sequence

import json_repair
from pydantic import BaseModel, Field, ValidationError

from deeptrace.context.retrieval import ChunkSelection
from deeptrace.models import CompressionOutcome, RawDocument, ResearchNote, ResearchTimeRange, SourceKind, TokenUsage
from deeptrace.context.temporal import normalize_temporal_relation
from deeptrace.prompts.compression import build_compression_messages


class ResearchNotePayload(BaseModel):
    """压缩模型必须返回的最小结构，不接受空笔记。"""
    title: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    evidence_snippets: list[str] = Field(min_length=1)
    event_start_date: date | None = None
    event_end_date: date | None = None
    source_kind: SourceKind = "unknown"
    temporal_scope: str = ""


@dataclass(frozen=True, slots=True)
class CompressionRequest:
    """一项可独立并发执行的网页压缩请求。"""
    tool_call_id: str
    order: int
    document: RawDocument
    selection: ChunkSelection
    active_query: str
    task_id: str
    section_id: str
    time_range: ResearchTimeRange | None = None


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


def _note_id(doc_id: str, active_query: str, task_id: str) -> str:
    digest = hashlib.sha256(
        f"{doc_id}\0{active_query}\0{task_id}".encode("utf-8")
    ).hexdigest()
    return f"note-{digest[:20]}"


def build_extractive_note(
    document: RawDocument,
    selection: ChunkSelection,
    active_query: str,
    task_id: str,
    section_id: str,
    error: str,
    time_range: ResearchTimeRange | None = None,
) -> ResearchNote:
    """压缩最终失败时直接保留全部入选块，保证已抓信息不丢失。"""
    snippets = [chunk.text for chunk in selection.chunks if chunk.text.strip()]
    return ResearchNote(
        note_id=_note_id(document.doc_id, active_query, task_id),
        doc_id=document.doc_id,
        task_id=task_id,
        section_id=section_id,
        active_query=active_query,
        title=document.title or document.final_url,
        key_points=snippets[:3] or ["未提取到相关正文"],
        evidence_snippets=snippets or ["未提取到相关正文"],
        source_url=document.final_url,
        relevance_score=selection.top1_fused_score,
        compression_status="extractive_fallback",
        error=error,
        source_published_at=document.source_published_at,
        source_kind="unknown",
        temporal_relation="unknown" if time_range else "not_applicable",
        temporal_scope="抽取式降级无法可靠确定事件时间" if time_range else "",
    )


class CompressionService:
    """有界并发调用 LLM；单页失败不会取消同批其他页面。"""

    def __init__(
        self,
        model: Any,
        concurrency: int = 3,
        timeout_seconds: float = 60.0,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency 必须大于 0")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        self._model = model
        self._semaphore = asyncio.Semaphore(concurrency)
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _messages(request: CompressionRequest) -> list[Any]:
        return build_compression_messages(
            active_query=request.active_query,
            title=request.document.title,
            url=request.document.final_url,
            chunks=[
                (chunk.index, chunk.text) for chunk in request.selection.chunks
            ],
            time_range=request.time_range,
            source_published_at=request.document.source_published_at,
            publisher=request.document.publisher,
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
            note_id=_note_id(
                request.document.doc_id, request.active_query, request.task_id
            ),
            doc_id=request.document.doc_id,
            task_id=request.task_id,
            section_id=request.section_id,
            active_query=request.active_query,
            title=request.document.title or request.document.final_url,
            key_points=[],
            evidence_snippets=[],
            source_url=request.document.final_url,
            relevance_score=request.selection.top1_fused_score,
            compression_status="irrelevant",
            source_published_at=request.document.source_published_at,
            temporal_relation="unknown" if request.time_range else "not_applicable",
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
                    response = await asyncio.wait_for(
                        self._model.ainvoke(messages),
                        timeout=self._timeout_seconds,
                    )
                    usage = self._usage(response)
                    total_usage = TokenUsage(
                        input_tokens=total_usage.input_tokens + usage.input_tokens,
                        output_tokens=total_usage.output_tokens + usage.output_tokens,
                        total_tokens=total_usage.total_tokens + usage.total_tokens,
                    )
                    payload = parse_note_json(self._message_text(response))
                    relation = normalize_temporal_relation(
                        request.time_range,
                        request.document.source_published_at,
                        payload.event_start_date,
                        payload.event_end_date,
                    )
                    note = ResearchNote(
                        note_id=_note_id(
                            request.document.doc_id,
                            request.active_query,
                            request.task_id,
                        ),
                        doc_id=request.document.doc_id,
                        task_id=request.task_id,
                        section_id=request.section_id,
                        active_query=request.active_query,
                        title=payload.title,
                        key_points=payload.key_points,
                        evidence_snippets=payload.evidence_snippets,
                        source_url=request.document.final_url,
                        relevance_score=request.selection.top1_fused_score,
                        compression_status="compressed",
                        source_published_at=request.document.source_published_at,
                        event_start_date=payload.event_start_date,
                        event_end_date=payload.event_end_date,
                        source_kind=payload.source_kind,
                        temporal_relation=relation,
                        temporal_scope=payload.temporal_scope,
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
                request.document,
                request.selection,
                request.active_query,
                request.task_id,
                request.section_id,
                last_error,
                request.time_range,
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
                        request.document,
                        request.selection,
                        request.active_query,
                        request.task_id,
                        request.section_id,
                        error,
                        request.time_range,
                    ),
                    error=error,
                    order=request.order,
                )
            outcomes.append(result)
        return sorted(outcomes, key=lambda item: item.order)
