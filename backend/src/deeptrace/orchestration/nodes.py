"""Node implementations for the Basic research graph."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
import time
from typing import Any

from deeptrace.agent.planner import PlannerAgent, normalize_question
from deeptrace.agent.writer import WriterAgent
from deeptrace.models import RunEvent, TokenUsage, UsageBreakdown
from deeptrace.observability import estimate_usage_cost
from deeptrace.orchestration.budget import GlobalBudget
from deeptrace.orchestration.research import ParallelResearchService, QueryResearchResult
from deeptrace.orchestration.state import GraphState


class ResearchWorkflowNodes:
    """Coordinate one planning, collection, and writing pass."""

    def __init__(
        self,
        *,
        planner: PlannerAgent,
        collector: ParallelResearchService,
        writer: WriterAgent,
        settings: Any,
        budget: GlobalBudget | None = None,
        on_event: Callable[[RunEvent], None] | None = None,
    ) -> None:
        self.planner = planner
        self.collector = collector
        self.writer = writer
        self.settings = settings
        self.budget = budget
        self._on_event = on_event

    def _event(
        self,
        event_type: str,
        message: str,
        *,
        details: Mapping[str, str | int | float | bool | None] | None = None,
    ) -> RunEvent:
        event = RunEvent(
            event_type=event_type,
            message=message,
            details=dict(details or {}),
        )
        if self._on_event is not None:
            self._on_event(event)
        return event

    async def _usage_update(self, role: str, usage: TokenUsage) -> dict[str, Any]:
        role_usage = UsageBreakdown(**{role: usage})
        cost = estimate_usage_cost(
            usage,
            getattr(self.settings, "input_cost_per_million", None),
            getattr(self.settings, "output_cost_per_million", None),
        )
        if self.budget is not None:
            await self.budget.record_usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=float(cost or Decimal(0)),
                now=datetime.now(UTC),
            )
        return {
            "api_token_count": usage.total_tokens,
            "provider_usage": usage,
            "role_usage": role_usage,
            "estimated_cost_usd": float(cost or Decimal(0)),
        }

    async def plan_node(self, state: GraphState) -> dict[str, Any]:
        started = time.perf_counter()
        question = state["user_query"]
        events = [self._event("planning.started", "开始生成搜索查询")]
        initial_search = await self.collector.asearch_initial(question)
        initial_results: Sequence[Mapping[str, Any]] = []
        if initial_search.get("ok") and isinstance(initial_search.get("results"), list):
            initial_results = initial_search["results"]
        budget_reason = (
            self.budget.stop_reason(datetime.now(UTC))
            if self.budget is not None
            else None
        )
        remaining = (
            self.budget.remaining_seconds(datetime.now(UTC))
            if self.budget is not None and budget_reason is None
            else 0.0
        )
        if budget_reason is not None or (
            self.budget is not None and remaining <= 0
        ):
            queries = [normalize_question(question)]
            usage = TokenUsage()
            used_fallback = True
            error = budget_reason or "time_budget"
        else:
            try:
                operation = self.planner.aplan(question, initial_results)
                if self.budget is None:
                    queries, usage, used_fallback, error = await operation
                else:
                    queries, usage, used_fallback, error = await asyncio.wait_for(
                        operation, timeout=remaining
                    )
            except TimeoutError:
                if self.budget is not None:
                    self.budget.stop_reason(datetime.now(UTC))
                queries = [normalize_question(question)]
                usage = TokenUsage()
                used_fallback = True
                error = "time_budget"
        events.append(
            self._event(
                "planning.completed",
                f"搜索查询已生成：{'；'.join(queries)}",
                details={"query_count": len(queries)},
            )
        )
        if used_fallback:
            events.append(
                self._event(
                    "planning.fallback",
                    "Planner 失败，降级为原始问题",
                    details={"error": error},
                )
            )
        return {
            "initial_search": initial_search,
            "search_queries": queries,
            "events": events,
            "stage_seconds": {"plan": time.perf_counter() - started},
            "step_count": 1,
            **await self._usage_update("planner", usage),
        }

    async def parallel_research_node(self, state: GraphState) -> dict[str, Any]:
        started = time.perf_counter()
        queries = list(state.get("search_queries", []))
        events = [
            self._event(
                "query.started",
                f"开始研究：{query}",
                details={"query": query},
            )
            for query in queries
        ]
        context, documents, sources, results = await self.collector.acollect(
            state["user_query"], queries, state.get("initial_search")
        )
        for result in results:
            events.append(self._query_completed_event(result))
        events.append(
            self._event(
                "research.completed",
                f"并行研究完成：{len(sources)} 个来源",
                details={
                    "query_count": len(queries),
                    "source_count": len(sources),
                },
            )
        )
        reason = ""
        if self.budget is not None:
            reason = self.budget.stop_reason(datetime.now(UTC)) or ""
        return {
            "documents": documents,
            "research_context": context,
            "final_sources": sources,
            "events": events,
            "fetched_page_count": len(documents),
            "force_finalize": bool(reason),
            "termination_reason": reason,
            "stage_seconds": {
                "parallel_research": time.perf_counter() - started
            },
            "step_count": 1,
        }

    def _query_completed_event(self, result: QueryResearchResult) -> RunEvent:
        return self._event(
            "query.completed",
            (
                f"研究完成：{result.query}；候选 {result.candidate_count}；"
                f"正文 {result.fetch_success_count}；失败 {result.fetch_failure_count}"
            ),
            details={
                "query": result.query,
                "candidate_count": result.candidate_count,
                "fetch_success_count": result.fetch_success_count,
                "fetch_failure_count": result.fetch_failure_count,
                "error_count": len(result.errors),
            },
        )

    async def writer_node(self, state: GraphState) -> dict[str, Any]:
        started = time.perf_counter()
        budget_reason = (
            self.budget.stop_reason(datetime.now(UTC))
            if self.budget is not None
            else None
        )
        reason = state.get("termination_reason") or budget_reason or "completed"
        if not state.get("research_context") and reason == "completed":
            reason = "no_sources"
        writer_input = {
            "question": state["user_query"],
            "context": state.get("research_context", ""),
            "sources": state.get("final_sources", []),
            "language": "zh-CN",
            "termination_reason": reason,
        }
        remaining = (
            self.budget.remaining_seconds(datetime.now(UTC))
            if self.budget is not None and budget_reason is None
            else 0.0
        )
        if budget_reason is not None or (
            self.budget is not None and remaining <= 0
        ):
            reason = budget_reason or "time_budget"
            writer_input["termination_reason"] = reason
            outcome = self.writer.fallback(**writer_input)
        else:
            try:
                operation = self.writer.awrite(**writer_input)
                if self.budget is None:
                    outcome = await operation
                else:
                    outcome = await asyncio.wait_for(operation, timeout=remaining)
            except TimeoutError:
                if self.budget is not None:
                    self.budget.stop_reason(datetime.now(UTC))
                reason = "time_budget"
                writer_input["termination_reason"] = reason
                outcome = self.writer.fallback(**writer_input)
        events = [self._event("writing.completed", "研究报告已生成")]
        if outcome.used_fallback:
            events.append(
                self._event(
                    "writing.fallback",
                    "Writer 失败，使用确定性降级报告",
                )
            )
        events.append(self._event("run.completed", "研究任务完成"))
        return {
            "final_answer": outcome.markdown,
            "final_sources": outcome.sources,
            "termination_reason": reason,
            "events": events,
            "stage_seconds": {"writer": time.perf_counter() - started},
            "step_count": 1,
            **await self._usage_update("writer", outcome.usage),
        }
