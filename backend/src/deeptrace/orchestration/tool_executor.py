"""阶段 3 的任务感知外部工具执行器。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from typing import Any, Sequence

from langchain_core.messages import BaseMessage, ToolMessage

from deeptrace.context import (
    CompressionRequest,
    CompressionRuntime,
    CompressionService,
    chunk_document,
    is_repeated_query,
    select_relevant_chunks,
)
from deeptrace.config import Settings
from deeptrace.models import (
    DocumentChunk,
    PendingFetch,
    RawDocument,
    ResearchNote,
    TokenUsage,
)
from deeptrace.observability import TokenLedger, estimate_usage_cost
from deeptrace.orchestration.state import GraphState
from deeptrace.tools import ToolContext, search_web
from deeptrace.tools.scraper import (
    AsyncWebFetcher,
    WebFetchError,
    normalize_url_before_fetch,
)


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """一个已完成的工具结果；order 仅用于并发 fan-in。"""

    tool_call_id: str
    order: int
    payload: dict[str, Any]


def build_tool_messages(
    tool_calls: Sequence[dict[str, Any]],
    results: Sequence[ToolCallResult],
) -> list[ToolMessage]:
    """按原调用顺序回填结果，不依赖并发完成顺序。"""
    by_id = {result.tool_call_id: result for result in results}
    messages: list[ToolMessage] = []
    for call in tool_calls:
        call_id = str(call.get("id", ""))
        result = by_id.get(call_id)
        payload = result.payload if result else {
            "ok": False,
            "error": {"code": "missing_result", "message": "工具结果缺失"},
        }
        messages.append(
            ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id=call_id,
                name=str(call.get("name", "")) or None,
            )
        )
    return messages


def keep_recent_tool_turns(
    messages: Sequence[BaseMessage], max_turns: int = 3
) -> list[BaseMessage]:
    """只保留最近完整的 AI tool_calls 与对应 ToolMessage。"""
    from langchain_core.messages import AIMessage

    turns: list[list[BaseMessage]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if not isinstance(message, AIMessage) or not message.tool_calls:
            index += 1
            continue
        expected = {str(call["id"]) for call in message.tool_calls}
        group: list[BaseMessage] = [message]
        seen: set[str] = set()
        cursor = index + 1
        while cursor < len(messages) and isinstance(messages[cursor], ToolMessage):
            tool_message = messages[cursor]
            group.append(tool_message)
            seen.add(str(tool_message.tool_call_id))
            cursor += 1
        if seen == expected:
            turns.append(group)
        index = cursor
    return [item for turn in turns[-max_turns:] for item in turn]


@dataclass(slots=True)
class ToolExecutionUpdate:
    """外部工具批次的显式增量。"""

    messages: list[ToolMessage] = field(default_factory=list)
    documents: dict[str, RawDocument] = field(default_factory=dict)
    chunks: dict[str, DocumentChunk] = field(default_factory=dict)
    notes: dict[str, ResearchNote] = field(default_factory=dict)
    attempted_queries: list[str] = field(default_factory=list)
    active_query: str = ""
    new_note_count: int = 0
    fetched_page_delta: int = 0
    errors: list[str] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    estimated_cost_delta: float = 0.0

    def as_state_update(self) -> dict[str, Any]:
        return {
            "documents": self.documents,
            "chunks": self.chunks,
            "notes": self.notes,
            "active_query": self.active_query,
            "fetched_page_count": self.fetched_page_delta,
            "recent_new_note_count": self.new_note_count,
            "api_token_count": self.usage.total_tokens,
            "provider_usage": self.usage,
            "estimated_cost_usd": self.estimated_cost_delta,
            "tool_outputs": {
                str(message.tool_call_id): str(message.content)
                for message in self.messages
            },
        }


def _note_payload(note: ResearchNote) -> dict[str, Any]:
    return {
        "ok": True,
        "type": "research_note",
        "relevant": note.compression_status != "irrelevant",
        "title": note.title,
        "key_points": note.key_points,
        "evidence_snippets": note.evidence_snippets,
        "source_url": note.source_url,
        "relevance_score": round(note.relevance_score, 4),
        "compression_status": note.compression_status,
    }


class ResearchToolExecutor:
    """执行搜索、抓取、召回和压缩，节点只合并返回增量。"""

    def __init__(
        self,
        *,
        runtime: CompressionRuntime,
        compressor: CompressionService,
        fetcher: AsyncWebFetcher,
        tools: ToolContext,
        ledger: TokenLedger,
        settings: Settings,
    ) -> None:
        self.runtime = runtime
        self.compressor = compressor
        self.fetcher = fetcher
        self.tools = tools
        self.ledger = ledger
        self.settings = settings

    @staticmethod
    def _task_identity(state: GraphState) -> tuple[str, str, list[str]]:
        plan = state.get("research_plan")
        index = state.get("current_task_index", 0)
        if plan is None or index >= len(plan.tasks):
            return "task-01", "section-01", list(state.get("queries", []))
        task = plan.tasks[index]
        coverage = state.get("task_coverages", {}).get(task.task_id)
        attempted = coverage.attempted_queries if coverage else []
        return task.task_id, task.section_id, list(attempted)

    @staticmethod
    def _existing_document(
        url: str, documents: Sequence[RawDocument]
    ) -> RawDocument | None:
        try:
            normalized = normalize_url_before_fetch(url)
        except ValueError:
            return None
        for document in documents:
            if normalized in {
                document.requested_url,
                document.final_url,
                document.canonical_url,
            }:
                return document
        return None

    async def _fetch_one(
        self, pending: PendingFetch, documents: Sequence[RawDocument]
    ) -> tuple[RawDocument | WebFetchError, bool]:
        existing = self._existing_document(pending.url, documents)
        if existing is not None:
            return existing, False
        try:
            return await self.fetcher.fetch(pending.url), True
        except WebFetchError as exc:
            return exc, False
        except Exception as exc:
            return WebFetchError(
                "fetch_failed", f"抓取失败：{type(exc).__name__}"
            ), False

    async def aexecute(
        self,
        state: GraphState,
        tool_calls: Sequence[dict[str, Any]],
    ) -> ToolExecutionUpdate:
        task_id, section_id, attempted_history = self._task_identity(state)
        results: list[ToolCallResult] = []
        accepted_queries: list[str] = []
        errors: list[str] = []

        for order, call in enumerate(tool_calls):
            if call.get("name") != "search_web":
                continue
            query = str(call.get("args", {}).get("query", "")).strip()
            max_results = call.get("args", {}).get("max_results", 5)
            invalid = (
                not query
                or not isinstance(max_results, int)
                or isinstance(max_results, bool)
            )
            if invalid:
                payload = {"ok": False, "error": {"code": "invalid_arguments", "message": "搜索参数无效"}}
            else:
                repeated = query in attempted_history or await asyncio.to_thread(
                    is_repeated_query,
                    self.runtime,
                    query,
                    attempted_history,
                    self.settings.query_loop_threshold,
                )
                if repeated:
                    payload = {"ok": False, "error": {"code": "duplicate_query", "message": "查询与当前任务历史重复"}}
                else:
                    accepted_queries.append(query)
                    attempted_history.append(query)
                    payload = await asyncio.to_thread(
                        search_web, self.tools, query, max_results
                    )
                    if payload.get("ok"):
                        self.ledger.record_search_tool(
                            json.dumps(payload, ensure_ascii=False)
                        )
            if not payload.get("ok"):
                errors.append(str(payload.get("error", {}).get("code", "search_failed")))
            results.append(ToolCallResult(str(call.get("id", "")), order, payload))

        active_query = accepted_queries[-1] if accepted_queries else (
            state.get("active_query") or state["user_query"]
        )
        pending: list[PendingFetch] = []
        for order, call in enumerate(tool_calls):
            name = call.get("name")
            if name == "fetch_webpage":
                url = str(call.get("args", {}).get("url", "")).strip()
                if url:
                    pending.append(PendingFetch(
                        tool_call_id=str(call.get("id", "")), url=url,
                        active_query=active_query, task_id=task_id,
                        section_id=section_id, order=order,
                    ))
                else:
                    results.append(ToolCallResult(str(call.get("id", "")), order, {"ok": False, "error": {"code": "invalid_arguments", "message": "url 不能为空"}}))
            elif name not in {"search_web", "complete_research_task"}:
                results.append(ToolCallResult(str(call.get("id", "")), order, {"ok": False, "error": {"code": "unknown_tool", "message": f"未知工具：{name}"}}))
            elif name == "complete_research_task":
                results.append(ToolCallResult(str(call.get("id", "")), order, {"ok": False, "error": {"code": "completion_not_external", "message": "完成工具必须由路由处理"}}))

        current_documents = list(state.get("documents", {}).values())
        fetched = await asyncio.gather(
            *(self._fetch_one(item, current_documents) for item in pending)
        )
        documents: dict[str, RawDocument] = {}
        pairs: list[tuple[PendingFetch, RawDocument]] = []
        fetched_delta = 0
        for item, (value, is_new) in zip(pending, fetched, strict=True):
            if isinstance(value, WebFetchError):
                payload = value.to_dict()
                results.append(ToolCallResult(item.tool_call_id, item.order, payload))
                errors.append(str(payload.get("error", {}).get("code", "fetch_failed")))
                continue
            if is_new:
                fetched_delta += 1
                documents[value.doc_id] = value
            pairs.append((item, value))

        chunks: dict[str, DocumentChunk] = {}
        for _item, document in pairs:
            existing = [chunk for chunk in state.get("chunks", {}).values() if chunk.doc_id == document.doc_id]
            if not existing:
                for chunk in chunk_document(self.runtime, document):
                    chunks[chunk.chunk_id] = chunk
        if chunks:
            await asyncio.to_thread(self.runtime.register_chunks, list(chunks.values()))

        requests: list[CompressionRequest] = []
        reused: dict[str, ResearchNote] = {}
        for item, document in pairs:
            cached = next((note for note in state.get("notes", {}).values() if note.doc_id == document.doc_id and note.task_id == task_id and note.active_query == item.active_query), None)
            if cached is not None:
                reused[item.tool_call_id] = cached
                continue
            document_chunks = [chunk for chunk in [*state.get("chunks", {}).values(), *chunks.values()] if chunk.doc_id == document.doc_id]
            selection = await asyncio.to_thread(
                select_relevant_chunks, self.runtime, document_chunks,
                state["user_query"], item.active_query, 6,
                self.settings.min_relevance_score,
            )
            requests.append(CompressionRequest(
                tool_call_id=item.tool_call_id, order=item.order,
                document=document, selection=selection,
                active_query=item.active_query, task_id=task_id,
                section_id=section_id,
            ))

        outcomes = await self.compressor.compress_many(requests)
        by_id = {outcome.tool_call_id: outcome for outcome in outcomes}
        total_usage = TokenUsage(
            input_tokens=sum(item.usage.input_tokens for item in outcomes),
            output_tokens=sum(item.usage.output_tokens for item in outcomes),
            total_tokens=sum(item.usage.total_tokens for item in outcomes),
        )
        estimated_cost = estimate_usage_cost(
            total_usage,
            self.settings.input_cost_per_million,
            self.settings.output_cost_per_million,
        )
        notes: dict[str, ResearchNote] = {}
        new_note_count = 0
        for item, document in pairs:
            note = reused.get(item.tool_call_id)
            outcome = by_id.get(item.tool_call_id)
            if note is None and outcome is not None:
                note = outcome.note
                self.ledger.record_compression_usage(outcome.usage)
                if note is not None:
                    notes[note.note_id] = note
                    new_note_count += 1
            if note is None:
                results.append(ToolCallResult(item.tool_call_id, item.order, {"ok": False, "error": {"code": "compression_failed", "message": "压缩结果缺失"}}))
                errors.append("compression_failed")
                continue
            payload = _note_payload(note)
            self.ledger.record_fetch_pair(
                json.dumps({"url": document.final_url, "content": document.content}, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
            )
            results.append(ToolCallResult(item.tool_call_id, item.order, payload))

        return ToolExecutionUpdate(
            messages=build_tool_messages(tool_calls, results),
            documents=documents,
            chunks=chunks,
            notes=notes,
            attempted_queries=accepted_queries,
            active_query=active_query,
            new_note_count=new_note_count,
            fetched_page_delta=fetched_delta,
            errors=errors,
            usage=total_usage,
            estimated_cost_delta=float(estimated_cost or 0),
        )
