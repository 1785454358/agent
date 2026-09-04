"""LangGraph 节点：模型决策、工具执行、网页压缩和上下文控制。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Literal, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from deeptrace.context import (
    CompressionRuntime,
    CompressionRequest,
    CompressionService,
    chunk_document,
    is_repeated_query,
    retrieve_notes,
    select_relevant_chunks,
)
from deeptrace.config import Settings
from deeptrace.models import (
    ContextAudit,
    DocumentChunk,
    PendingFetch,
    RawDocument,
    ResearchNote,
    TokenUsage,
)
from deeptrace.prompts.research import FINAL_REPORT_PROMPT, build_system_prompt
from deeptrace.orchestration.state import GraphState
from deeptrace.observability import TokenLedger, format_round_metrics
from deeptrace.tools import ToolContext, search_web
from deeptrace.tools.scraper import (
    AsyncWebFetcher,
    WebFetchError,
    normalize_url_before_fetch,
)


def select_agent_model_mode(
    *,
    step: int,
    soft_max_steps: int,
    hard_max_steps: int,
    extension_granted: bool,
    can_extend: bool,
    has_notes: bool,
) -> Literal["agent", "finalize", "refuse"]:
    """在调用模型前决定继续研究或直接汇总，保证每轮只调用一次模型。"""
    should_end = step >= hard_max_steps or (
        step >= soft_max_steps and not extension_granted and not can_extend
    )
    if should_end:
        return "finalize" if has_notes else "refuse"
    return "agent"


def build_unverified_finalization(step: int) -> dict[str, Any]:
    """无验证笔记时返回确定性限制，不让模型依据搜索摘要编造报告。"""
    return {
        "step_count": step,
        "final_answer": (
            "未在预算内获得成功抓取的研究笔记，不能把搜索摘要当事实。"
            "请调整查询或抓取来源后重试。"
        ),
        "termination_reason": "no_verified_sources",
        "events": [f"步骤 {step}：无已验证研究笔记，拒绝生成报告"],
    }


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
    """按原调用顺序回填结果，绝不依赖并发任务的完成顺序。"""
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
    """只保留最近完整的 AI tool_calls + 对应 ToolMessage 组合。"""
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
    return [message for turn in turns[-max_turns:] for message in turn]


def _usage(message: Any) -> TokenUsage:
    metadata = getattr(message, "usage_metadata", None) or {}
    input_tokens = int(metadata.get("input_tokens", 0) or 0)
    output_tokens = int(metadata.get("output_tokens", 0) or 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=int(
            metadata.get("total_tokens", input_tokens + output_tokens)
            or input_tokens + output_tokens
        ),
    )


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    return json.dumps(content, ensure_ascii=False)


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


class ResearchNodes:
    """一次研究运行共享的节点服务与进程内向量缓存。"""

    def __init__(
        self,
        *,
        bound_model: Any,
        final_model: Any,
        runtime: CompressionRuntime,
        compressor: CompressionService,
        fetcher: AsyncWebFetcher,
        tools: ToolContext,
        ledger: TokenLedger,
        settings: Settings,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.bound_model = bound_model
        self.final_model = final_model
        self.runtime = runtime
        self.compressor = compressor
        self.fetcher = fetcher
        self.tools = tools
        self.ledger = ledger
        self.settings = settings
        self.on_event = on_event or (lambda _event: None)
        self._baseline_initialized = False
        self._pending_embedding_tokens = 0

    async def _prompt(self, state: GraphState) -> list[BaseMessage]:
        base: list[BaseMessage] = [
            SystemMessage(content=build_system_prompt()),
            HumanMessage(content=state["user_query"]),
        ]
        notes = list(state.get("notes", {}).values())
        if notes:
            selected = await asyncio.to_thread(
                retrieve_notes,
                self.runtime,
                notes,
                state["user_query"],
                state.get("active_query") or state["user_query"],
                8,
            )
            note_text = "\n\n".join(
                json.dumps(_note_payload(note), ensure_ascii=False) for note in selected
            )
            base.append(SystemMessage(content=f"当前相关研究笔记：\n{note_text}"))
        return [*base, *state.get("messages", [])]

    async def agent_node(self, state: GraphState) -> dict[str, Any]:
        """预算判断先于模型调用；研究轮和收尾轮每轮都只调用一次模型。"""
        step = state.get("step_count", 0) + 1
        self.on_event(f"[步骤 {step}] 主 Agent 决策")
        prompt = await self._prompt(state)
        if not self._baseline_initialized:
            self.ledger.record_initial_context(prompt[:2])
            self._baseline_initialized = True

        extension = state.get("extension_granted", False)
        can_extend = False
        if (
            step >= self.settings.soft_max_steps
            and step < self.settings.hard_max_steps
            and not extension
        ):
            gaps = state.get("unresolved_gaps", [])
            candidate = (
                gaps[0].strip()
                if gaps
                else (state.get("active_query") or "").strip()
            )
            repeated = True
            if candidate:
                repeated = await asyncio.to_thread(
                    is_repeated_query,
                    self.runtime,
                    candidate,
                    state.get("queries", []),
                    self.settings.query_loop_threshold,
                )
            can_extend = (
                state.get("recent_new_note_count", 0) > 0
                and bool(candidate)
                and not repeated
            )

        mode = select_agent_model_mode(
            step=step,
            soft_max_steps=self.settings.soft_max_steps,
            hard_max_steps=self.settings.hard_max_steps,
            extension_granted=extension,
            can_extend=can_extend,
            has_notes=bool(state.get("notes")),
        )
        if can_extend and not extension:
            extension = True
            self.on_event("[预算] 批准一次延长，最多继续到硬上限")
        if mode == "refuse":
            self.on_event("[预算] 无已验证研究笔记，拒绝生成最终报告")
            return build_unverified_finalization(step)
        model_prompt = (
            [*prompt, HumanMessage(content=FINAL_REPORT_PROMPT)]
            if mode == "finalize"
            else prompt
        )
        model = self.final_model if mode == "finalize" else self.bound_model
        if mode == "finalize":
            self.on_event(f"[步骤 {step}] 研究预算到达，生成最终报告")
        try:
            response = await model.ainvoke(model_prompt)
        except Exception as exc:
            raise RuntimeError(f"主模型请求失败：{type(exc).__name__}") from exc
        if not isinstance(response, AIMessage):
            response = AIMessage(content=_message_text(response))

        usage = _usage(response)
        metrics = self.ledger.finish_round(
            round_index=step,
            actual_messages=model_prompt,
            provider_usage=usage,
            local_embedding_tokens=self._pending_embedding_tokens,
        )
        self._pending_embedding_tokens = 0
        self.on_event(format_round_metrics(metrics))
        self.ledger.record_assistant(response)

        serialized_prompt = "\n".join(
            _message_text(item) for item in model_prompt
        )
        raw_matches = sum(
            1
            for document in state.get("documents", {}).values()
            if document.content and document.content in serialized_prompt
        )
        audit = ContextAudit(
            round_index=step,
            input_tokens=metrics.estimated_actual_context_tokens,
            raw_content_match_count=raw_matches,
        )

        if mode == "finalize":
            answer = _message_text(response)
            if not answer:
                raise RuntimeError("最终报告模型未返回内容")
            return {
                "step_count": step,
                "final_answer": answer,
                "termination_reason": "completed",
                "extension_granted": extension,
                "token_metrics": [metrics],
                "context_audits": [audit],
                "events": [f"步骤 {step}：生成最终报告"],
            }

        if response.tool_calls:
            return {
                "messages": [*state.get("messages", []), response],
                "step_count": step,
                "extension_granted": extension,
                "token_metrics": [metrics],
                "context_audits": [audit],
            }
        answer = _message_text(response)
        if not answer:
            raise RuntimeError("模型既未调用工具，也未返回答案")
        return {
            "step_count": step,
            "final_answer": answer,
            "termination_reason": "completed",
            "token_metrics": [metrics],
            "context_audits": [audit],
        }

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
    ) -> RawDocument | WebFetchError:
        existing = self._existing_document(pending.url, documents)
        if existing is not None:
            return existing
        try:
            return await self.fetcher.fetch(pending.url)
        except WebFetchError as exc:
            return exc
        except Exception as exc:
            return WebFetchError("fetch_failed", f"抓取失败：{type(exc).__name__}")

    async def tools_node(self, state: GraphState) -> dict[str, Any]:
        """执行短搜索回填；并发抓取后批量向量化、筛选和压缩。"""
        last = state.get("messages", [])[-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            raise RuntimeError("tools 节点缺少 AI tool_calls")
        calls = list(last.tool_calls)
        results: list[ToolCallResult] = []
        queries: list[str] = []

        for order, call in enumerate(calls):
            if call.get("name") != "search_web":
                continue
            args = call.get("args", {})
            query = str(args.get("query", "")).strip()
            max_results = args.get("max_results", 5)
            if not query or not isinstance(max_results, int) or isinstance(max_results, bool):
                payload = {"ok": False, "error": {"code": "invalid_arguments", "message": "搜索参数无效"}}
            else:
                payload = await asyncio.to_thread(
                    search_web, self.tools, query, max_results
                )
                if payload.get("ok"):
                    queries.append(query)
                    self.ledger.record_search_tool(
                        json.dumps(payload, ensure_ascii=False)
                    )
            results.append(ToolCallResult(str(call["id"]), order, payload))

        active_query = queries[-1] if queries else (
            state.get("active_query") or state["user_query"]
        )
        pending: list[PendingFetch] = []
        for order, call in enumerate(calls):
            name = call.get("name")
            if name == "fetch_webpage":
                url = str(call.get("args", {}).get("url", "")).strip()
                if not url:
                    results.append(ToolCallResult(
                        str(call["id"]), order,
                        {"ok": False, "error": {"code": "invalid_arguments", "message": "url 不能为空"}},
                    ))
                else:
                    pending.append(PendingFetch(
                        tool_call_id=str(call["id"]), url=url,
                        active_query=active_query, task_id="task-01",
                        section_id="section-01", order=order,
                    ))
            elif name != "search_web":
                results.append(ToolCallResult(
                    str(call["id"]), order,
                    {"ok": False, "error": {"code": "unknown_tool", "message": f"未知工具：{name}"}},
                ))

        current_documents = list(state.get("documents", {}).values())
        fetched = await asyncio.gather(
            *(self._fetch_one(item, current_documents) for item in pending),
            return_exceptions=False,
        )
        documents_update: dict[str, RawDocument] = {}
        chunks_update: dict[str, DocumentChunk] = {}
        request_pairs: list[tuple[PendingFetch, RawDocument]] = []
        for item, value in zip(pending, fetched, strict=True):
            if isinstance(value, WebFetchError):
                results.append(ToolCallResult(item.tool_call_id, item.order, value.to_dict()))
                continue
            documents_update[value.doc_id] = value
            request_pairs.append((item, value))

        # 所有新页面的 chunks 一次批量 embedding，避免逐页加载与调用。
        for _item, document in request_pairs:
            existing_chunks = [
                chunk for chunk in state.get("chunks", {}).values()
                if chunk.doc_id == document.doc_id
            ]
            if not existing_chunks:
                for chunk in chunk_document(self.runtime, document):
                    chunks_update[chunk.chunk_id] = chunk
        if chunks_update:
            new_chunks = list(chunks_update.values())
            await asyncio.to_thread(self.runtime.register_chunks, new_chunks)
            self._pending_embedding_tokens += sum(c.token_count for c in new_chunks)

        compression_requests: list[CompressionRequest] = []
        reused_notes: dict[str, ResearchNote] = {}
        notes = list(state.get("notes", {}).values())
        for item, document in request_pairs:
            cached_note = next(
                (
                    note for note in notes
                    if note.doc_id == document.doc_id
                    and note.active_query == item.active_query
                ),
                None,
            )
            if cached_note is not None:
                reused_notes[item.tool_call_id] = cached_note
                continue
            document_chunks = [
                chunk
                for chunk in [*state.get("chunks", {}).values(), *chunks_update.values()]
                if chunk.doc_id == document.doc_id
            ]
            selection = await asyncio.to_thread(
                select_relevant_chunks,
                self.runtime,
                document_chunks,
                state["user_query"],
                item.active_query,
                6,
                self.settings.min_relevance_score,
            )
            self._pending_embedding_tokens += self.runtime.count_tokens(
                state["user_query"]
            ) + self.runtime.count_tokens(item.active_query)
            compression_requests.append(CompressionRequest(
                tool_call_id=item.tool_call_id,
                order=item.order,
                document=document,
                selection=selection,
                active_query=item.active_query,
                task_id=item.task_id,
                section_id=item.section_id,
            ))

        outcomes = await self.compressor.compress_many(compression_requests)
        outcome_by_id = {outcome.tool_call_id: outcome for outcome in outcomes}
        notes_update: dict[str, ResearchNote] = {}
        new_note_count = 0
        for item, document in request_pairs:
            note = reused_notes.get(item.tool_call_id)
            outcome = outcome_by_id.get(item.tool_call_id)
            if note is None and outcome is not None:
                note = outcome.note
                self.ledger.record_compression_usage(outcome.usage)
                if note is not None:
                    notes_update[note.note_id] = note
                    new_note_count += 1
            if note is None:
                results.append(ToolCallResult(
                    item.tool_call_id, item.order,
                    {"ok": False, "error": {"code": "compression_failed", "message": "压缩结果缺失"}},
                ))
                continue
            payload = _note_payload(note)
            self.ledger.record_fetch_pair(
                json.dumps(
                    {"url": document.final_url, "content": document.content},
                    ensure_ascii=False,
                ),
                json.dumps(payload, ensure_ascii=False),
            )
            results.append(ToolCallResult(item.tool_call_id, item.order, payload))

        tool_messages = build_tool_messages(calls, results)
        history = keep_recent_tool_turns(
            [*state.get("messages", []), *tool_messages],
            max_turns=3,
        )
        outputs = {
            message.tool_call_id: str(message.content) for message in tool_messages
        }
        return {
            "messages": history,
            "documents": documents_update,
            "chunks": chunks_update,
            "notes": notes_update,
            "queries": queries,
            "active_query": active_query,
            "pending_fetches": [],
            "pending_tool_order": [],
            "tool_outputs": outputs,
            "recent_new_note_count": new_note_count,
            "events": [f"执行 {len(calls)} 个工具调用，新增 {new_note_count} 条笔记"],
        }


# 阶段 3 节点只协调角色服务与领域服务；旧 ResearchNodes 保留到 Task 7 完成组装迁移。
from datetime import UTC, datetime

from deeptrace.agent._shared import add_usage
from deeptrace.agent.planner import PlannerAgent
from deeptrace.agent.researcher import ResearcherAgent, parse_task_completion
from deeptrace.agent.writer import WriterAgent
from deeptrace.context import retrieve_notes
from deeptrace.models import (
    ResearchPlan,
    RunEvent,
    SectionResult,
    TaskCompletion,
    TaskCoverage,
    UsageBreakdown,
)
from deeptrace.orchestration.budget import GlobalBudget
from deeptrace.orchestration.state import (
    append_unique,
    merge_dicts,
    merge_stage_seconds,
    merge_token_usage,
    merge_usage_breakdown,
)
from deeptrace.orchestration.coverage import complete_coverage, forced_coverage
from deeptrace.orchestration.quality import note_is_valid, summarize_note_quality
from deeptrace.orchestration.tool_executor import (
    ResearchToolExecutor,
    keep_recent_tool_turns as keep_stage3_tool_turns,
)
from deeptrace.observability import estimate_usage_cost


class ResearchWorkflowNodes:
    """阶段 3 的轻量 LangGraph 节点集合。"""

    def __init__(
        self,
        *,
        planner: PlannerAgent,
        researcher: ResearcherAgent,
        writer: WriterAgent,
        executor: ResearchToolExecutor,
        settings: Settings,
        runtime: CompressionRuntime,
        on_event: Callable[[RunEvent], None] | None = None,
    ) -> None:
        self.planner = planner
        self.researcher = researcher
        self.writer = writer
        self.executor = executor
        self.settings = settings
        self.runtime = runtime
        self.budget: GlobalBudget | None = None
        self.on_event = on_event or (lambda _event: None)

    def _event(
        self, event_type: str, message: str, task_id: str | None = None
    ) -> RunEvent:
        event = RunEvent(event_type=event_type, message=message, task_id=task_id)
        self.on_event(event)
        return event

    def _usage_update(self, role: str, usage: TokenUsage) -> dict[str, Any]:
        cost = estimate_usage_cost(
            usage,
            self.settings.input_cost_per_million,
            self.settings.output_cost_per_million,
        )
        return {
            "api_token_count": usage.total_tokens,
            "provider_usage": usage,
            "role_usage": UsageBreakdown(**{role: usage}),
            "estimated_cost_usd": float(cost or 0),
        }

    def _research_error_update(
        self, task: Any, coverage: TaskCoverage, exc: Exception
    ) -> dict[str, Any]:
        reason = f"researcher_error:{type(exc).__name__}"
        return {
            "pending_task_completion": TaskCompletion(
                task_id=task.task_id,
                summary="researcher_error",
                covered_topics=coverage.covered_topics,
                unresolved_topics=coverage.missing_topics or task.expected_topics,
            ),
            "task_coverages": {
                task.task_id: coverage.model_copy(
                    update={"failure_reason": reason}
                )
            },
            "events": [
                self._event(
                    "task.failed",
                    f"研究模型调用失败：{type(exc).__name__}",
                    task.task_id,
                )
            ],
        }

    @staticmethod
    def _current(state: GraphState) -> tuple[ResearchPlan, Any, TaskCoverage]:
        plan = state.get("research_plan")
        if plan is None:
            raise RuntimeError("研究计划缺失")
        index = state.get("current_task_index", 0)
        if index >= len(plan.tasks):
            raise RuntimeError("当前任务索引越界")
        task = plan.tasks[index]
        coverage = state.get("task_coverages", {}).get(task.task_id)
        if coverage is None:
            raise RuntimeError(f"任务覆盖状态缺失：{task.task_id}")
        return plan, task, coverage

    async def plan_node(self, state: GraphState) -> dict[str, Any]:
        started = time.perf_counter()
        plan, usage, used_fallback, planner_error = await self.planner.aplan(
            state["user_query"]
        )
        planner_seconds = time.perf_counter() - started
        coverages = {
            task.task_id: TaskCoverage(task_id=task.task_id)
            for task in plan.tasks
        }
        events = [
            self._event(
                "planning.completed",
                "研究计划已生成："
                + "；".join(
                    f"{index}. {task.title}"
                    for index, task in enumerate(plan.tasks, start=1)
                ),
            )
        ]
        if used_fallback:
            events.append(
                self._event(
                    "planning.fallback",
                    f"结构化规划失败，使用单任务降级计划：{planner_error}",
                )
            )
        return {
            "research_plan": plan,
            "task_coverages": coverages,
            "current_task_index": 0,
            "step_count": state.get("step_count", 0) + 1,
            "events": events,
            "stage_seconds": {"planner": planner_seconds},
            **self._usage_update("planner", usage),
        }

    async def start_task_node(self, state: GraphState) -> dict[str, Any]:
        _plan, task, coverage = self._current(state)
        running = coverage.model_copy(
            update={"status": "running", "failure_reason": None}
        )
        return {
            "active_query": task.question,
            "messages": [],
            "pending_task_completion": None,
            "task_coverages": {task.task_id: running},
            "events": [
                self._event(
                    "task.started", f"开始研究：{task.title}", task.task_id
                )
            ],
        }

    async def research_node(self, state: GraphState) -> dict[str, Any]:
        _plan, task, coverage = self._current(state)
        reason = (
            self.budget.stop_reason(datetime.now(UTC))
            if self.budget is not None
            else None
        )
        force_finalize = reason is not None
        if reason is None and coverage.rounds >= getattr(
            self.settings, "max_task_rounds", 3
        ):
            reason = "task_round_budget"
        if reason is None and coverage.consecutive_empty_rounds >= 2:
            reason = "consecutive_empty_rounds"
        if reason is not None:
            pending = TaskCompletion(
                task_id=task.task_id,
                summary=reason,
                covered_topics=coverage.covered_topics,
                unresolved_topics=coverage.missing_topics or task.expected_topics,
            )
            return {
                "pending_task_completion": pending,
                "force_finalize": force_finalize,
                "termination_reason": reason if force_finalize else state.get("termination_reason", ""),
                "task_coverages": {
                    task.task_id: coverage.model_copy(
                        update={"failure_reason": reason}
                    )
                },
                "events": [
                    self._event(
                        "budget.reached", f"任务停止：{reason}", task.task_id
                    )
                ],
            }

        task_notes = [
            note
            for note in state.get("notes", {}).values()
            if note.task_id == task.task_id
        ]
        selected = await asyncio.to_thread(
            retrieve_notes,
            self.runtime,
            task_notes,
            state["user_query"],
            task.question,
            8,
        ) if task_notes else []
        recent = keep_stage3_tool_turns(state.get("messages", []), max_turns=3)
        researcher_seconds = 0.0
        try:
            started = time.perf_counter()
            response, usage = await self.researcher.adecide(
                user_query=state["user_query"],
                task=task,
                coverage=coverage,
                notes=selected,
                recent_messages=recent,
                budget_summary=(
                    f"当前第 {coverage.rounds + 1} 轮，"
                    f"最多 {getattr(self.settings, 'max_task_rounds', 3)} 轮"
                ),
            )
            researcher_seconds += time.perf_counter() - started
        except Exception as exc:
            return self._research_error_update(task, coverage, exc)
        total_usage = usage
        if not response.tool_calls:
            correction = HumanMessage(
                content=(
                    "你既未调用外部工具也未完成任务。"
                    "请立即调用所需工具，或调用 complete_research_task。"
                )
            )
            try:
                started = time.perf_counter()
                response, retry_usage = await self.researcher.adecide(
                    user_query=state["user_query"], task=task,
                    coverage=coverage, notes=selected,
                    recent_messages=[*recent, response, correction],
                    budget_summary="这是本轮唯一纠正机会",
                )
                researcher_seconds += time.perf_counter() - started
            except Exception as exc:
                return self._research_error_update(task, coverage, exc)
            total_usage = add_usage(total_usage, retry_usage)

        pending: TaskCompletion | None = None
        for call in response.tool_calls:
            if call.get("name") == "complete_research_task":
                try:
                    pending = parse_task_completion(call, task.task_id)
                except (ValueError, TypeError) as exc:
                    pending = TaskCompletion(
                        task_id=task.task_id,
                        summary="invalid_task_completion",
                        unresolved_topics=task.expected_topics,
                    )
                break
        if not response.tool_calls:
            pending = TaskCompletion(
                task_id=task.task_id,
                summary="researcher_no_action",
                unresolved_topics=task.expected_topics,
            )
        updated = coverage.model_copy(update={"rounds": coverage.rounds + 1})
        return {
            "messages": [*recent, response],
            "pending_task_completion": pending,
            "task_coverages": {task.task_id: updated},
            "step_count": state.get("step_count", 0) + 1,
            "stage_seconds": {"researcher": researcher_seconds},
            **self._usage_update("researcher", total_usage),
        }

    async def tools_node(self, state: GraphState) -> dict[str, Any]:
        _plan, task, coverage = self._current(state)
        last = state.get("messages", [])[-1]
        if not isinstance(last, AIMessage):
            raise RuntimeError("tools 节点缺少 AIMessage")
        calls = [
            call
            for call in last.tool_calls
            if call.get("name") in {"search_web", "fetch_webpage"}
        ]
        result = await self.executor.aexecute(state, calls)
        useful = [
            note
            for note in result.notes.values()
            if note.compression_status != "irrelevant"
        ]
        valid = [note for note in useful if note_is_valid(note)]
        quality = summarize_note_quality(useful)
        sources = list(
            dict.fromkeys(
                [*coverage.successful_source_urls, *(note.source_url for note in valid)]
            )
        )
        note_ids = list(
            dict.fromkeys(
                [*coverage.relevant_note_ids, *(note.note_id for note in useful)]
            )
        )
        next_coverage = coverage.model_copy(
            update={
                "attempted_queries": list(
                    dict.fromkeys(
                        [*coverage.attempted_queries, *result.attempted_queries]
                    )
                ),
                "successful_source_urls": sources,
                "relevant_note_ids": note_ids,
                "consecutive_empty_rounds": (
                    0
                    if result.new_note_count
                    else coverage.consecutive_empty_rounds + 1
                ),
                "failure_reason": result.errors[0] if result.errors else None,
            }
        )
        update = result.as_state_update()
        update.update(
            {
                "messages": keep_stage3_tool_turns(
                    [*state.get("messages", []), *result.messages], max_turns=3
                ),
                "task_coverages": {task.task_id: next_coverage},
                "events": [
                    self._event(
                        "tools.completed",
                        (
                            f"搜索候选 {result.search_candidate_count}；抓取成功 {result.fetch_success_count}，"
                            f"失败 {result.fetch_failure_count}，跳过 {result.skipped_count}；有效笔记 {len(valid)}；"
                            f"后发回顾 {len(quality.retrospective_ids)}，"
                            f"时间未知 {len(quality.unknown_ids)}，"
                            f"超出范围 {len(quality.out_of_range_ids)}；失败码 {result.error_counts or '无'}"
                        ),
                        task.task_id,
                    )
                ],
            }
        )
        return update

    async def complete_task_node(self, state: GraphState) -> dict[str, Any]:
        _plan, task, coverage = self._current(state)
        completion = state.get("pending_task_completion")
        if completion is None:
            messages = state.get("messages", [])
            last = messages[-1] if messages else None
            if isinstance(last, AIMessage):
                call = next(
                    (
                        item
                        for item in last.tool_calls
                        if item.get("name") == "complete_research_task"
                    ),
                    None,
                )
                if call is not None:
                    completion = parse_task_completion(call, task.task_id)
        notes = [
            note
            for note in state.get("notes", {}).values()
            if note.task_id == task.task_id
        ]
        forced_reason = coverage.failure_reason
        if completion is None:
            forced_reason = forced_reason or "missing_task_completion"
        if forced_reason and (
            completion is None or completion.summary == forced_reason
        ):
            final_coverage = forced_coverage(
                task, coverage, notes, forced_reason
            )
            summary = completion.summary if completion else forced_reason
        else:
            assert completion is not None
            final_coverage = complete_coverage(
                task,
                coverage,
                completion,
                notes,
                [coverage.failure_reason] if coverage.failure_reason else [],
            )
            summary = completion.summary
        section = SectionResult(
            task_id=task.task_id,
            section_id=task.section_id,
            title=task.title,
            summary=summary,
            note_ids=final_coverage.valid_note_ids,
            source_urls=final_coverage.qualified_source_urls,
            coverage=final_coverage,
            errors=[forced_reason] if forced_reason else [],
        )
        return {
            "task_coverages": {task.task_id: final_coverage},
            "section_results": {task.task_id: section},
            "pending_task_completion": None,
            "events": [
                self._event(
                    "task.research_completed",
                    f"研究阶段结束，正在生成章节结果：{task.title}",
                    task.task_id,
                )
            ],
        }

    async def finalize_task_node(
        self, state: GraphState
    ) -> dict[str, Any]:
        """推进任务索引一次，冻结章节结果。"""
        _plan, task, _coverage = self._current(state)
        section = state.get("section_results", {}).get(task.task_id)
        if section is None:
            raise RuntimeError("待冻结章节缺失")
        return {
            "section_results": {task.task_id: section},
            "current_task_index": state.get("current_task_index", 0) + 1,
            "pending_task_completion": None,
            "messages": [],
            "events": [
                self._event(
                    "task.completed",
                    f"研究任务结束：{task.title}",
                    task.task_id,
                )
            ],
        }

    async def research_all_node(self, state: GraphState) -> dict[str, Any]:
        """并行执行全部子任务；每条任务管线独立成状态，预算经网关竞争。"""
        plan = state.get("research_plan")
        if plan is None:
            raise RuntimeError("研究计划缺失")
        concurrency = max(
            1, min(getattr(self.settings, "task_concurrency", 2), len(plan.tasks))
        )
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(index: int) -> dict[str, Any]:
            async with semaphore:
                return await self._run_single_task(state, index)

        updates = await asyncio.gather(
            *(run_one(index) for index in range(len(plan.tasks)))
        )
        merged = self._merge_task_updates(updates)
        merged["termination_reason"] = (
            self.budget.reason if self.budget is not None else None
        ) or "completed"
        return merged

    async def _run_single_task(
        self, state: GraphState, index: int
    ) -> dict[str, Any]:
        """单个子任务的完整管线：研究轮循环 → 章节 → 冻结。"""
        plan = state["research_plan"]
        task = plan.tasks[index]
        accumulated: dict[str, Any] = {
            "events": [
                self._event(
                    "task.started", f"开始研究：{task.title}", task.task_id
                )
            ]
        }
        task_state: dict[str, Any] = {
            **state,
            "current_task_index": index,
            "messages": [],
            "pending_task_completion": None,
            "force_finalize": False,
            "step_count": 0,
            "task_coverages": {
                task.task_id: TaskCoverage(
                    task_id=task.task_id, status="running"
                )
            },
            # 跨任务共享交给执行器级缓存；任务本地只保留自己的增量。
            "documents": {},
            "chunks": {},
            "notes": {},
            "queries": [],
            "termination_reason": "",
        }
        rounds_allowed = getattr(self.settings, "max_task_rounds", 3)
        for _round in range(rounds_allowed + 1):
            update = await self.research_node(task_state)
            self._merge_update(accumulated, update)
            self._merge_update(task_state, update)
            if update.get("pending_task_completion") is not None:
                break
            if update.get("force_finalize"):
                break
            tool_update = await self.tools_node(task_state)
            self._merge_update(accumulated, tool_update)
            self._merge_update(task_state, tool_update)
        complete_update = await self.complete_task_node(task_state)
        self._merge_update(accumulated, complete_update)
        self._merge_update(task_state, complete_update)
        finalize_update = await self.finalize_task_node(task_state)
        self._merge_update(accumulated, finalize_update)
        return accumulated

    _LOCAL_REDUCERS: dict[str, Any] = {
        "documents": merge_dicts,
        "chunks": merge_dicts,
        "notes": merge_dicts,
        "queries": append_unique,
        "task_coverages": merge_dicts,
        "section_results": merge_dicts,
        "provider_usage": merge_token_usage,
        "role_usage": merge_usage_breakdown,
        "stage_seconds": merge_stage_seconds,
    }

    def _merge_update(
        self, accumulated: dict[str, Any], update: dict[str, Any]
    ) -> None:
        """按父图 reducer 语义把节点增量合并进累计字典。"""
        for key, value in update.items():
            reducer = self._LOCAL_REDUCERS.get(key)
            if reducer is None:
                if key in {"events", "context_audits", "token_metrics"}:
                    accumulated.setdefault(key, [])
                    accumulated[key] = [*accumulated[key], *value]
                elif key in {"api_token_count", "estimated_cost_usd", "step_count", "fetched_page_count"}:
                    accumulated[key] = accumulated.get(key, 0) + value
                else:
                    accumulated[key] = value
            else:
                accumulated[key] = (
                    value if accumulated.get(key) is None else reducer(accumulated[key], value)
                )

    def _merge_task_updates(
        self, updates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for update in updates:
            self._merge_update(merged, update)
        return merged

    async def writer_node(self, state: GraphState) -> dict[str, Any]:
        plan = state.get("research_plan")
        if plan is None:
            raise RuntimeError("Writer 缺少研究计划")
        by_task = state.get("section_results", {})
        sections = [by_task[task.task_id] for task in plan.tasks if task.task_id in by_task]
        notes = state.get("notes", {})
        notes_by_section = {
            task.task_id: [
                note
                for note in notes.values()
                if note.task_id == task.task_id
                and note.compression_status != "irrelevant"
            ]
            for task in plan.tasks
        }
        reason = state.get("termination_reason") or "completed"
        outcome = await self.writer.awrite(
            plan=plan,
            sections=sections,
            notes_by_section=notes_by_section,
            termination_reason=reason,
        )
        events = [self._event("writing.completed", "研究报告已生成")]
        if outcome.used_fallback:
            events.append(self._event("writing.fallback", "Writer 失败，使用确定性降级报告"))
        events.append(self._event("run.completed", "研究任务完成"))
        return {
            "final_answer": outcome.markdown,
            "final_sources": outcome.sources,
            "used_note_ids": outcome.used_note_ids,
            "termination_reason": reason,
            "events": events,
            **self._usage_update("writer", outcome.usage),
        }
