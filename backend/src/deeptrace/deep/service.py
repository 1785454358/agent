"""Assemble the Deep research pipeline dependencies."""

from __future__ import annotations

from collections.abc import Callable

from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from deeptrace.writer import WriterAgent
from deeptrace.config import Settings
from deeptrace.context import CompressionRuntime, ContextCompressor
from deeptrace.deep.agent import DeepResearchAgent
from deeptrace.deep.tools import ResearchToolbox
from deeptrace.memory import ResearchMemory
from deeptrace.models import RunEvent
from deeptrace.tools import ToolContext, search_web
from deeptrace.tools.scraper import AsyncWebFetcher


def build_deep_agent(
    settings: Settings,
    on_event: Callable[[RunEvent], None] | None = None,
) -> DeepResearchAgent:
    """Assemble the Provider, search, scraper, embeddings, and Deep agent."""
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
    tool_context = ToolContext(tavily=TavilyClient(api_key=settings.tavily_api_key))

    def search(query):
        return search_web(
            tool_context, query, settings.max_search_results_per_query, None
        )

    return DeepResearchAgent(
        model=model,
        writer=WriterAgent(
            model, call_timeout_seconds=settings.writer_timeout_seconds
        ),
        tools=ResearchToolbox(
            search=search,
            fetcher=fetcher,
            compressor=compressor,
            settings=settings,
            runtime=runtime,
            memory=ResearchMemory(settings.memory_path)
            if settings.use_memory
            else None,
        ),
        settings=settings,
        on_event=on_event,
    )
