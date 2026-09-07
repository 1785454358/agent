"""Assemble the Basic research pipeline dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from deeptrace.basic.agent import ResearchAgent
from deeptrace.basic.planner import PlannerAgent
from deeptrace.writer import WriterAgent
from deeptrace.config import Settings
from deeptrace.context import CompressionRuntime, ContextCompressor
from deeptrace.memory import ResearchMemory
from deeptrace.models import RunEvent
from deeptrace.basic.graph import build_research_graph
from deeptrace.basic.nodes import ResearchWorkflowNodes
from deeptrace.basic.research import ParallelResearchService
from deeptrace.tools import ToolContext
from deeptrace.tools.scraper import AsyncWebFetcher


def build_basic_agent(
    settings: Settings,
    on_event: Callable[[RunEvent], None] | None = None,
) -> ResearchAgent:
    """Assemble the Provider, search, scraper, embeddings, and Basic graph."""
    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0,
        max_tokens=settings.openai_max_tokens,
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
        similarity_threshold=getattr(settings, "context_similarity_threshold", 0.42),
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
