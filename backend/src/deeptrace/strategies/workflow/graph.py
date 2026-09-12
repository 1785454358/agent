"""Compilation of the Workflow research strategy subgraph."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.workflow.nodes import (
    build_plan_queries_node,
    build_research_topic_node,
    evaluate_node,
    finalize_node,
    route_topics,
)
from deeptrace.strategies.workflow.state import TopicBranchState, WorkflowState


def build_workflow_research_graph(
    topic_graph,
    *,
    query_limit: int = 3,
    checkpointer=None,
) -> CompiledStateGraph:
    builder = StateGraph(WorkflowState, context_schema=HarnessContext)
    builder.add_node("plan_queries", build_plan_queries_node(query_limit))
    builder.add_node(
        "research_topic",
        build_research_topic_node(topic_graph),
        input_schema=TopicBranchState,
    )
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge(START, "plan_queries")
    builder.add_conditional_edges("plan_queries", route_topics)
    builder.add_edge("research_topic", "evaluate")
    builder.add_edge("evaluate", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
