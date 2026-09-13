"""Compilation of the reusable research topic subgraph."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from langgraph.graph.state import CompiledStateGraph

from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.topic.nodes import (
    fetch_page_node,
    finalize_node,
    route_fetches,
    search_node,
    select_urls_node,
)
from deeptrace.strategies.topic.state import FetchBranchState, ResearchTopicState


def build_research_topic_graph(checkpointer=None) -> CompiledStateGraph:
    builder = StateGraph(ResearchTopicState, context_schema=HarnessContext)
    from deeptrace.strategies.topic.nodes import TransientToolError

    retry = RetryPolicy(max_attempts=3, retry_on=(TransientToolError,))
    builder.add_node("search", search_node, retry_policy=retry)
    builder.add_node("select_urls", select_urls_node)
    builder.add_node(
        "fetch_page",
        fetch_page_node,
        input_schema=FetchBranchState,
        retry_policy=retry,
    )
    builder.add_node("finalize", finalize_node)
    builder.add_edge(START, "search")
    builder.add_edge("search", "select_urls")
    builder.add_conditional_edges("select_urls", route_fetches)
    builder.add_edge("fetch_page", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
