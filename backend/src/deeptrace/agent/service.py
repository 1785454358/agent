"""Public facade and real dependency assembly for Basic research."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from deeptrace.agent.planner import PlannerAgent
from deeptrace.agent.writer import WriterAgent
from deeptrace.config import Settings
from deeptrace.context import CompressionRuntime, ContextCompressor
from deeptrace.memory import ResearchMemory
from deeptrace.models import RunEvent, TokenUsage, UsageBreakdown
from deeptrace.observability import estimate_usage_cost
from deeptrace.orchestration.budget import GlobalBudget
from deeptrace.orchestration.graph import build_research_graph
from deeptrace.orchestration.nodes import ResearchWorkflowNodes
from deeptrace.orchestration.research import ParallelResearchService
from deeptrace.tools import ToolContext
from deeptrace.tools.scraper import AsyncWebFetcher


@dataclass(frozen=True)
class AgentResult:
    """The final public result of one Basic research run."""

    status: Literal["completed", "partial", "failed"]
    answer: str
    sources: list[str]
    steps: int
    events: list[RunEvent]
    termination_reason: str
    search_queries: list[str]
    provider_usage: TokenUsage
    role_usage: UsageBreakdown
    estimated_cost_usd: Decimal | None
    stage_seconds: dict[str, float]


def _initial_research_state(
    question: str, *, started_at: datetime | None = None
) -> dict[str, Any]:
    """Create a complete state value for a new graph invocation."""
    started = started_at or datetime.now(UTC)
    return {
        "user_query": question,
        "search_queries": [],
        "initial_search": None,
        "documents": {},
        "research_context": "",
        "final_sources": [],
        "events": [],
        "started_at": started.isoformat(),
        "fetched_page_count": 0,
        "api_token_count": 0,
        "estimated_cost_usd": 0.0,
        "provider_usage": TokenUsage(),
        "role_usage": UsageBreakdown(),
        "stage_seconds": {},
        "step_count": 0,
        "force_finalize": False,
        "final_answer": "",
        "termination_reason": "",
    }


class ResearchAgent:
    """Run the graph while keeping transport layers independent of LangGraph."""

    def __init__(
        self,
        *,
        graph: Any,
        nodes: ResearchWorkflowNodes,
        collector: ParallelResearchService,
        fetcher: AsyncWebFetcher,
        settings: Settings,
    ) -> None:
        self._graph = graph
        self._nodes = nodes
        self._collector = collector
        self._fetcher = fetcher
        self._settings = settings

    async def arun(self, question: str) -> AgentResult:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空")

        started_at = datetime.now(UTC)
        budget = GlobalBudget(self._settings, started_at)
        self._nodes.budget = budget
        self._collector.budget = budget

        memory: ResearchMemory | None = None
        if getattr(self._settings, "use_memory", False):
            memory = ResearchMemory(self._settings.memory_path)
            self._collector.cache_documents(
                [memory.entry_to_document(entry) for entry in memory.entries()]
            )

        final = await self._graph.ainvoke(
            _initial_research_state(clean_question, started_at=started_at),
            config={
                "configurable": {"service": self._nodes},
                "recursion_limit": 10,
            },
        )
        if memory is not None:
            memory.add_documents(list(final.get("documents", {}).values()))

        reason = final.get("termination_reason") or "completed"
        answer = final.get("final_answer", "")
        sources = list(final.get("final_sources", []))
        if reason == "completed" and answer and sources:
            status: Literal["completed", "partial", "failed"] = "completed"
        elif answer:
            status = "partial"
        else:
            status = "failed"
        usage = final.get("provider_usage", TokenUsage())
        return AgentResult(
            status=status,
            answer=answer,
            sources=sources,
            steps=final.get("step_count", 0),
            events=list(final.get("events", [])),
            termination_reason=reason,
            search_queries=list(final.get("search_queries", [])),
            provider_usage=usage,
            role_usage=final.get("role_usage", UsageBreakdown()),
            estimated_cost_usd=estimate_usage_cost(
                usage,
                getattr(self._settings, "input_cost_per_million", None),
                getattr(self._settings, "output_cost_per_million", None),
            ),
            stage_seconds=dict(final.get("stage_seconds", {})),
        )

    def run(self, question: str) -> AgentResult:
        return asyncio.run(self.arun(question))

    async def aclose(self) -> None:
        await self._fetcher.aclose()


def build_real_agent(
    settings: Settings,
    on_event: Callable[[RunEvent], None] | None = None,
) -> ResearchAgent:
    """Assemble the Provider, search, scraper, embeddings, and Basic graph."""
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
        min_chars=settings.min_extracted_chars,
        min_tokens=settings.min_extracted_tokens,
        max_page_chars=settings.max_page_chars,
        allow_benchmark_dns_proxy=settings.allow_benchmark_dns_proxy,
    )
    compressor = ContextCompressor(
        runtime,
        direct_threshold_chars=getattr(
            settings, "context_direct_threshold_chars", 8_000
        ),
        chunk_size=getattr(settings, "context_chunk_chars", 1_000),
        chunk_overlap=getattr(settings, "context_chunk_overlap_chars", 100),
        similarity_threshold=getattr(
            settings, "context_similarity_threshold", 0.42
        ),
    )
    collector = ParallelResearchService(
        tools=ToolContext(tavily=TavilyClient(api_key=settings.tavily_api_key)),
        fetcher=fetcher,
        compressor=compressor,
        settings=settings,
    )
    nodes = ResearchWorkflowNodes(
        planner=PlannerAgent(
            model,
            query_count=getattr(settings, "search_query_count", 3),
            call_timeout_seconds=getattr(settings, "planner_timeout_seconds", 60),
        ),
        collector=collector,
        writer=WriterAgent(
            model,
            call_timeout_seconds=getattr(settings, "writer_timeout_seconds", 60),
        ),
        settings=settings,
        on_event=on_event,
    )
    return ResearchAgent(
        graph=build_research_graph(),
        nodes=nodes,
        collector=collector,
        fetcher=fetcher,
        settings=settings,
    )
