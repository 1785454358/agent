"""DeepTrace 阶段 2 对外门面与真实依赖组装。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from typing import Any, Callable, Literal

from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from deeptrace.context import CompressionRuntime, CompressionService
from deeptrace.config import Settings
from deeptrace.tools.scraper import AsyncWebFetcher
from deeptrace.models import RoundTokenMetrics
from deeptrace.orchestration import ResearchNodes, build_research_graph
from deeptrace.observability import TokenEstimator, TokenLedger
from deeptrace.tools import EXTERNAL_TOOL_SCHEMAS, ToolContext


URL_PATTERN = re.compile(r"https?://[^\s<>\]\[()]+")


@dataclass(frozen=True)
class AgentResult:
    """一次研究任务的最终答案、来源及逐轮 Token 指标。"""

    status: Literal["completed", "max_steps_reached", "no_verified_sources"]
    answer: str
    sources: list[str]
    steps: int
    events: list[str]
    token_metrics: list[RoundTokenMetrics]
    termination_reason: str


def _clean_answer_urls(answer: str) -> str:
    return URL_PATTERN.sub("[来源见下方列表]", answer).strip()


class ResearchAgent:
    """封装 LangGraph，使 CLI 无需了解节点和状态细节。"""

    def __init__(
        self,
        *,
        graph: Any,
        nodes: ResearchNodes,
        fetcher: AsyncWebFetcher,
        settings: Settings,
    ) -> None:
        self._graph = graph
        self._nodes = nodes
        self._fetcher = fetcher
        self._settings = settings

    async def arun(self, question: str) -> AgentResult:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空")
        initial = {
            "user_query": clean_question,
            "active_query": clean_question,
            "messages": [],
            "documents": {},
            "chunks": {},
            "notes": {},
            "queries": [],
            "pending_fetches": [],
            "pending_tool_order": [],
            "tool_outputs": {},
            "events": [],
            "token_metrics": [],
            "context_audits": [],
            "step_count": 0,
            "extension_granted": False,
            "recent_new_note_count": 0,
            "unresolved_gaps": [],
            "final_answer": "",
            "termination_reason": "",
        }
        final = await self._graph.ainvoke(
            initial,
            config={
                "configurable": {"service": self._nodes},
                "recursion_limit": self._settings.hard_max_steps * 2 + 4,
            },
        )
        reason = final.get("termination_reason", "completed")
        if reason == "completed":
            status = "completed"
        elif reason == "no_verified_sources":
            status = "no_verified_sources"
        else:
            status = "max_steps_reached"
        sources = sorted(
            {document.final_url for document in final.get("documents", {}).values()}
        )
        return AgentResult(
            status=status,
            answer=_clean_answer_urls(final.get("final_answer", "")),
            sources=sources,
            steps=final.get("step_count", 0),
            events=list(final.get("events", [])),
            token_metrics=list(final.get("token_metrics", [])),
            termination_reason=reason,
        )

    def run(self, question: str) -> AgentResult:
        return asyncio.run(self.arun(question))

    async def aclose(self) -> None:
        await self._fetcher.aclose()


def build_real_agent(
    settings: Settings,
    on_event: Callable[[str], None] | None = None,
) -> ResearchAgent:
    """组装真实 ChatOpenAI、Tavily、BGE-M3、抓取器和 LangGraph。"""
    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0,
    )
    bound_model = model.bind_tools(EXTERNAL_TOOL_SCHEMAS)
    runtime = CompressionRuntime(
        settings.embedding_model_path,
        batch_size=settings.embedding_batch_size,
    )
    fetcher = AsyncWebFetcher(
        count_tokens=runtime.count_tokens,
        min_chars=settings.min_extracted_chars,
        min_tokens=settings.min_extracted_tokens,
        max_page_chars=settings.max_page_chars,
        allow_benchmark_dns_proxy=settings.allow_benchmark_dns_proxy,
    )
    nodes = ResearchNodes(
        bound_model=bound_model,
        final_model=model,
        runtime=runtime,
        compressor=CompressionService(runtime),
        fetcher=fetcher,
        tools=ToolContext(
            tavily=TavilyClient(api_key=settings.tavily_api_key),
        ),
        ledger=TokenLedger(TokenEstimator(settings.token_encoding)),
        settings=settings,
        on_event=on_event,
    )
    return ResearchAgent(
        graph=build_research_graph(),
        nodes=nodes,
        fetcher=fetcher,
        settings=settings,
    )


# 阶段 3 应用门面；保留上方阶段 2 定义仅用于历史提交可读性，公共名称在此迁移。
from datetime import UTC, datetime
from decimal import Decimal

from deeptrace.agent.planner import PlannerAgent
from deeptrace.agent.researcher import ResearcherAgent
from deeptrace.agent.writer import WriterAgent
from deeptrace.models import (
    ResearchNote,
    ResearchPlan,
    RunEvent,
    SectionResult,
    TokenUsage,
    UsageBreakdown,
)
from deeptrace.memory import ResearchMemory
from deeptrace.observability import estimate_usage_cost
from deeptrace.orchestration import ResearchWorkflowNodes
from deeptrace.orchestration.budget import GlobalBudget
from deeptrace.orchestration.tool_executor import ResearchToolExecutor


def _sources_from_used_notes(
    notes: dict[str, ResearchNote], used_note_ids: list[str]
) -> list[str]:
    """按 Writer 使用顺序生成去重来源，不泄漏未使用抓取页。"""
    sources: list[str] = []
    for note_id in used_note_ids:
        note = notes.get(note_id)
        if note is not None and note.source_url not in sources:
            sources.append(note.source_url)
    return sources


def _initial_research_state(
    question: str, started_at: datetime | None = None
) -> dict[str, Any]:
    """集中初始化完整 State，避免新增节点读取缺失键。"""
    return {
        "user_query": question,
        "active_query": question,
        "messages": [],
        "documents": {},
        "chunks": {},
        "notes": {},
        "queries": [],
        "pending_fetches": [],
        "pending_tool_order": [],
        "tool_outputs": {},
        "research_plan": None,
        "current_task_index": 0,
        "task_coverages": {},
        "section_results": {},
        "pending_task_completion": None,
        "force_finalize": False,
        "events": [],
        "started_at": (
            started_at if started_at is not None else datetime.now(UTC)
        ).isoformat(),
        "fetched_page_count": 0,
        "api_token_count": 0,
        "estimated_cost_usd": 0.0,
        "provider_usage": TokenUsage(),
        "role_usage": UsageBreakdown(),
        "used_note_ids": [],
        "token_metrics": [],
        "context_audits": [],
        "step_count": 0,
        "extension_granted": False,
        "recent_new_note_count": 0,
        "unresolved_gaps": [],
        "final_answer": "",
        "termination_reason": "",
    }


@dataclass(frozen=True)
class AgentResult:
    """阶段 3 的计划、章节、报告、来源与用量结果。"""

    status: Literal["completed", "partial", "failed"]
    answer: str
    sources: list[str]
    steps: int
    events: list[RunEvent]
    token_metrics: list[RoundTokenMetrics]
    termination_reason: str
    plan: ResearchPlan | None
    sections: list[SectionResult]
    used_note_ids: list[str]
    provider_usage: TokenUsage
    role_usage: UsageBreakdown
    estimated_cost_usd: Decimal | None


class ResearchAgent:
    """阶段 3 LangGraph 门面，CLI 不接触内部节点。"""

    def __init__(
        self,
        *,
        graph: Any,
        nodes: ResearchWorkflowNodes,
        fetcher: AsyncWebFetcher,
        settings: Settings,
    ) -> None:
        self._graph = graph
        self._nodes = nodes
        self._fetcher = fetcher
        self._settings = settings

    async def arun(self, question: str) -> AgentResult:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空")
        started_at = datetime.now(UTC)
        budget = GlobalBudget(self._settings, started_at)
        self._nodes.budget = budget
        self._nodes.executor.budget = budget
        memory = None
        if self._settings.use_memory:
            memory = ResearchMemory(self._settings.memory_path)
            for entry in memory.entries():
                document = memory.entry_to_document(entry)
                for key in {
                    document.requested_url,
                    document.final_url,
                    document.canonical_url,
                }:
                    if key:
                        self._nodes.executor._document_cache[key] = document
        initial = _initial_research_state(clean_question, started_at=started_at)
        final = await self._graph.ainvoke(
            initial,
            config={
                "configurable": {"service": self._nodes},
                "recursion_limit": (
                    self._settings.hard_max_steps * 4
                    + 20
                    + self._settings.max_research_tasks * 4
                ),
            },
        )
        plan = final.get("research_plan")
        by_task = final.get("section_results", {})
        sections = (
            [by_task[task.task_id] for task in plan.tasks if task.task_id in by_task]
            if plan
            else []
        )
        if memory is not None:
            memory.add_documents(final.get("documents", {}).values())
        reason = final.get("termination_reason") or "completed"
        answer = final.get("final_answer", "")
        has_material = bool(
            final.get("final_sources")
        ) or bool(final.get("used_note_ids"))
        if reason == "completed" and answer and has_material:
            status: Literal["completed", "partial", "failed"] = "completed"
        elif answer:
            status = "partial"
        else:
            status = "failed"
        used_note_ids = list(final.get("used_note_ids", []))
        usage = final.get("provider_usage", TokenUsage())
        role_usage = final.get("role_usage", UsageBreakdown())
        sources = list(final.get("final_sources", [])) or sorted(
            {
                document.final_url
                for document in final.get("documents", {}).values()
            }
        )
        return AgentResult(
            status=status,
            answer=answer,
            sources=sources,
            steps=final.get("step_count", 0),
            events=list(final.get("events", [])),
            token_metrics=list(final.get("token_metrics", [])),
            termination_reason=reason,
            plan=plan,
            sections=sections,
            used_note_ids=used_note_ids,
            provider_usage=usage,
            role_usage=role_usage,
            estimated_cost_usd=estimate_usage_cost(
                usage,
                self._settings.input_cost_per_million,
                self._settings.output_cost_per_million,
            ),
        )

    def run(self, question: str) -> AgentResult:
        return asyncio.run(self.arun(question))

    async def aclose(self) -> None:
        await self._fetcher.aclose()


def build_real_agent(
    settings: Settings,
    on_event: Callable[[RunEvent], None] | None = None,
) -> ResearchAgent:
    """组装真实 Planner、Researcher、Writer、工具执行器和 LangGraph。"""
    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0,
    )
    runtime = CompressionRuntime(
        settings.embedding_model_path,
        batch_size=settings.embedding_batch_size,
    )
    fetcher = AsyncWebFetcher(
        count_tokens=runtime.count_tokens,
        min_chars=settings.min_extracted_chars,
        min_tokens=settings.min_extracted_tokens,
        max_page_chars=settings.max_page_chars,
        allow_benchmark_dns_proxy=settings.allow_benchmark_dns_proxy,
    )
    compressor = CompressionService(runtime)
    ledger = TokenLedger(TokenEstimator(settings.token_encoding))
    executor = ResearchToolExecutor(
        runtime=runtime,
        compressor=compressor,
        fetcher=fetcher,
        tools=ToolContext(tavily=TavilyClient(api_key=settings.tavily_api_key)),
        ledger=ledger,
        settings=settings,
    )
    nodes = ResearchWorkflowNodes(
        planner=PlannerAgent(
            model,
            max_tasks=settings.max_research_tasks,
            queries_per_task=3,
            min_sources=settings.min_sources_per_task,
        ),
        researcher=ResearcherAgent(model),
        writer=WriterAgent(model),
        executor=executor,
        settings=settings,
        runtime=runtime,
        on_event=on_event,
    )
    return ResearchAgent(
        graph=build_research_graph(),
        nodes=nodes,
        fetcher=fetcher,
        settings=settings,
    )
