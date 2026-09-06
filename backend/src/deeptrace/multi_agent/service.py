"""Assemble dependencies for the Supervisor Multi-Agent research mode."""

from __future__ import annotations

from collections.abc import Callable

from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from deeptrace.config import Settings
from deeptrace.context import CompressionRuntime, ContextCompressor
from deeptrace.memory import ResearchMemory
from deeptrace.models import RunEvent
from deeptrace.multi_agent.agent import SupervisorResearchAgent
from deeptrace.multi_agent.graph import build_multi_agent_graph
from deeptrace.multi_agent.resources import SharedResearchResources
from deeptrace.tools import ToolContext, search_web
from deeptrace.tools.scraper import AsyncWebFetcher
from deeptrace.writer import WriterAgent


def build_multi_agent(
    settings: Settings,
    on_event: Callable[[RunEvent], None] | None = None,
) -> SupervisorResearchAgent:
    """Build one run-isolated Supervisor and its shared resource owner."""
    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0,
        max_tokens=settings.openai_max_tokens,
    )
    embeddings = CompressionRuntime(
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
        embeddings,
        direct_threshold_chars=settings.context_direct_threshold_chars,
        chunk_size=settings.context_chunk_chars,
        chunk_overlap=settings.context_chunk_overlap_chars,
        similarity_threshold=settings.context_similarity_threshold,
    )
    tool_context = ToolContext(tavily=TavilyClient(api_key=settings.tavily_api_key))

    def search(query):
        return search_web(
            tool_context, query, settings.max_search_results_per_query, None
        )

    resources = SharedResearchResources(
        search=search,
        fetcher=fetcher,
        compressor=compressor,
        embeddings=embeddings,
        memory=ResearchMemory(settings.multi_agent_memory_path)
        if settings.use_memory
        else None,
        settings=settings,
        total_tool_calls=settings.multi_agent_max_tool_calls,
        per_researcher_tool_calls=settings.multi_agent_max_tools_per_researcher,
    )
    return SupervisorResearchAgent(
        model=model,
        writer=WriterAgent(
            model, call_timeout_seconds=settings.writer_timeout_seconds
        ),
        resources=resources,
        settings=settings,
        on_event=on_event,
        graph=build_multi_agent_graph(),
    )
