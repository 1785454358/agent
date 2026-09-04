"""入选块按向量相似度确定性压缩为 ResearchNote，全程零 LLM 调用。

与 GPT-Researcher 的 compression 同思路：拆句、本地 embedding、按与双查询的
相似度过滤，只保留最相关的原句作为 key_points 与 evidence_snippets。压缩
不消耗任何 Provider token；事件时间改由入选句子中的日期规则提取。
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

import numpy as np

from deeptrace.context.embeddings import CompressionRuntime
from deeptrace.context.retrieval import ChunkSelection
from deeptrace.context.temporal import normalize_temporal_relation
from deeptrace.models import (
    CompressionOutcome,
    RawDocument,
    ResearchNote,
    ResearchTimeRange,
    TokenUsage,
)

_MAX_SENTENCE_CHARS = 220
_MIN_SENTENCE_CHARS = 12

# 主切分：句末标点或换行；长句再按逗号级切分，保证片段仍是原文连续文本。
_SENTENCE_PATTERN = re.compile(r"[^。！？!?；;\n\r]+[。！？!?；;]?")
_CLAUSE_PATTERN = re.compile(r"[^，,、]+[，,、]?")

# 中文与 ISO 风格日期：2024年10月23日 / 2024 年10月 / 2024年 / 2024-10-23 / 2024/10。
# 年份后必须有分隔符，避免在英文日期（October 23, 2024）上误匹配裸年份。
_DATE_PATTERN = re.compile(
    r"(?P<year>19\d{2}|20\d{2})[ \t]*[年\-/.]"
    r"(?:(?P<month>1[0-2]|0?[1-9])[ \t]*[月\-/.]"
    r"(?:(?P<day>3[01]|[12]\d|0?[1-9])[ \t]*日?)?)?"
)
_ENGLISH_DATE_PATTERN = re.compile(
    r"(?P<month_name>January|February|March|April|May|June|July|August|"
    r"September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|"
    r"Sept|Sep|Oct|Nov|Dec)"
    r"\.?\s+(?:(?P<day>3[01]|[12]\d|0?[1-9])(?:st|nd|rd|th)?,?\s+)?"
    r"(?P<year>19\d{2}|20\d{2})"
)
_ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12, "jan": 1, "feb": 2, "mar": 3,
    "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sept": 9, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


@dataclass(frozen=True, slots=True)
class CompressionRequest:
    """一项可独立并发执行的网页压缩请求。"""

    tool_call_id: str
    order: int
    document: RawDocument
    selection: ChunkSelection
    user_query: str
    active_query: str
    task_id: str
    section_id: str
    time_range: ResearchTimeRange | None = None


def _split_sentences(text: str) -> list[str]:
    """在句末标点与换行处切分；超长片段按逗号级二段切分，不改动原文。"""
    sentences: list[str] = []
    for raw in _SENTENCE_PATTERN.findall(text or ""):
        piece = raw.strip()
        if not piece:
            continue
        if len(piece) <= _MAX_SENTENCE_CHARS:
            sentences.append(piece)
            continue
        buffer = ""
        for part in _CLAUSE_PATTERN.findall(piece):
            buffer += part
            if len(buffer) >= _MAX_SENTENCE_CHARS:
                sentences.append(buffer.strip())
                buffer = ""
        if buffer.strip():
            sentences.append(buffer.strip())
    return sentences


def _candidate_sentences(chunks: Sequence[Any]) -> list[str]:
    """按块顺序展开句子，并对重叠块导致的重复句子去重。"""
    result: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        for sentence in _split_sentences(chunk.text):
            key = re.sub(r"\s+", "", sentence)
            if len(key) < _MIN_SENTENCE_CHARS or key in seen:
                continue
            seen.add(key)
            result.append(sentence)
    return result


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _span_for(year: int, month: int | None, day: int | None) -> tuple[date, date]:
    if month is None:
        return date(year, 1, 1), date(year, 12, 31)
    if day is None:
        return (
            date(year, month, 1),
            date(year, month, calendar.monthrange(year, month)[1]),
        )
    exact = _clamp_day(year, month, day)
    return exact, exact


def extract_event_dates(text: str) -> tuple[date | None, date | None]:
    """从入选句子提取事件时间跨度的确定性近似：最早与最晚日期。"""
    starts: list[date] = []
    ends: list[date] = []

    def _collect(match: re.Match[str]) -> None:
        year = int(match.group("year"))
        month_name = match.groupdict().get("month_name")
        month = (
            _ENGLISH_MONTHS.get(month_name.lower())
            if month_name
            else (int(match.group("month")) if match.group("month") else None)
        )
        day_text = match.group("day")
        day = int(day_text) if day_text else None
        start, end = _span_for(year, month, day)
        starts.append(start)
        ends.append(end)

    for pattern in (_DATE_PATTERN, _ENGLISH_DATE_PATTERN):
        for match in pattern.finditer(text):
            _collect(match)
    if not starts:
        return None, None
    return min(starts), max(ends)


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
    """压缩路径异常时直接保留全部入选块，保证已抓信息不丢失。"""
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
    """句子级向量过滤压缩：本地 embedding 打分，无模型调用、无 token 消耗。"""

    def __init__(
        self,
        runtime: CompressionRuntime,
        *,
        top_sentences: int = 8,
        sentence_threshold: float = 0.35,
    ) -> None:
        if top_sentences < 1:
            raise ValueError("top_sentences 必须大于 0")
        if not 0.0 <= sentence_threshold <= 1.0:
            raise ValueError("sentence_threshold 必须位于 [0, 1]")
        self._runtime = runtime
        self._top_sentences = top_sentences
        self._sentence_threshold = sentence_threshold

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

    def _compress_sync(self, request: CompressionRequest) -> CompressionOutcome:
        sentences = _candidate_sentences(request.selection.chunks)
        if not sentences:
            return CompressionOutcome(
                tool_call_id=request.tool_call_id,
                note=build_extractive_note(
                    request.document,
                    request.selection,
                    request.active_query,
                    request.task_id,
                    request.section_id,
                    "no_sentences",
                    request.time_range,
                ),
                error="no_sentences",
                order=request.order,
            )
        vectors = self._runtime.embed(sentences)
        active_scores = vectors @ self._runtime.query_vector(request.active_query)
        scores = active_scores
        if request.user_query.strip():
            user_scores = vectors @ self._runtime.query_vector(request.user_query)
            scores = np.maximum(user_scores, active_scores)

        ranked = np.argsort(-scores, kind="stable")
        selected = [
            int(index)
            for index in ranked
            if scores[index] >= self._sentence_threshold
        ][: self._top_sentences]
        if not selected:
            selected = [int(ranked[0])]

        evidence_snippets = [sentences[index] for index in sorted(selected)]
        key_points = [
            sentences[index]
            for index in sorted(selected[:3], key=lambda idx: -scores[idx])
        ]
        event_start, event_end = extract_event_dates(
            "\n".join(evidence_snippets)
        )
        relation = normalize_temporal_relation(
            request.time_range,
            request.document.source_published_at,
            event_start,
            event_end,
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
            title=request.document.title or request.document.final_url,
            key_points=key_points,
            evidence_snippets=evidence_snippets,
            source_url=request.document.final_url,
            relevance_score=request.selection.top1_fused_score,
            compression_status="compressed",
            source_published_at=request.document.source_published_at,
            event_start_date=event_start,
            event_end_date=event_end,
            source_kind="unknown",
            temporal_relation=relation,
        )
        return CompressionOutcome(
            tool_call_id=request.tool_call_id,
            note=note,
            order=request.order,
            usage=TokenUsage(),
        )

    async def compress_one(self, request: CompressionRequest) -> CompressionOutcome:
        """embedding 为 CPU 密集计算，放入线程避免阻塞事件循环。"""
        if not request.selection.is_relevant:
            return self._irrelevant_outcome(request)
        try:
            return await asyncio.to_thread(self._compress_sync, request)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            return CompressionOutcome(
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
