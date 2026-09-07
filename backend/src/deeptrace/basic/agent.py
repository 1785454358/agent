"""Basic research agent: run the LangGraph pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from deeptrace.config import Settings
from deeptrace.context import CompressionRuntime, ContextCompressor
from deeptrace.memory import ResearchMemory
from deeptrace.models import RunEvent, TokenUsage, UsageBreakdown
from deeptrace.observability import estimate_usage_cost
from deeptrace.basic.graph import build_research_graph
from deeptrace.basic.nodes import ResearchWorkflowNodes
from deeptrace.basic.research import ParallelResearchService
from deeptrace.models import AgentResult
from deeptrace.observability import GlobalBudget
from deeptrace.tools import ToolContext
from deeptrace.tools.scraper import AsyncWebFetcher


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
            unresolved_gaps=list(final.get("unresolved_gaps", [])),
        )

    def run(self, question: str) -> AgentResult:
        return asyncio.run(self.arun(question))

    async def aclose(self) -> None:
        await self._fetcher.aclose()
