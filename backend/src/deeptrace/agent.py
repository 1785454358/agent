"""DeepTrace 阶段 2 对外门面与真实依赖组装。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from typing import Any, Callable, Literal

from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from deeptrace.compression import CompressionService
from deeptrace.config import Settings
from deeptrace.embedding import CompressionRuntime
from deeptrace.fetching import AsyncWebFetcher
from deeptrace.graph import build_research_graph
from deeptrace.models import RoundTokenMetrics
from deeptrace.nodes import ResearchNodes
from deeptrace.token_metrics import TokenEstimator, TokenLedger
from deeptrace.tools import TOOL_SCHEMAS, ToolContext


URL_PATTERN = re.compile(r"https?://[^\s<>\]\[()]+")


@dataclass(frozen=True)
class AgentResult:
    """一次研究任务的最终答案、来源及逐轮 Token 指标。"""

    status: Literal["completed", "max_steps_reached"]
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
        status = "completed" if reason == "completed" else "max_steps_reached"
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
    bound_model = model.bind_tools(TOOL_SCHEMAS)
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
        runtime=runtime,
        compressor=CompressionService(
            model, concurrency=settings.compression_concurrency
        ),
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
