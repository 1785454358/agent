"""Compilation of the Multi-Agent research strategy subgraph."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.multi_agent.nodes import (
    aggregate_node,
    build_follow_up_node,
    build_finalize_node,
    build_researcher_node,
    build_route_after_evaluate,
    build_supervisor_plan_node,
    route_after_follow_up,
    route_researchers,
    supervisor_evaluate_node,
)
from deeptrace.strategies.multi_agent.state import MultiAgentState


def build_multi_agent_research_graph(
    topic_graph,
    *,
    max_researchers: int = 5,
    max_follow_ups: int = 1,
    checkpointer=None,
) -> CompiledStateGraph:
    builder = StateGraph(MultiAgentState, context_schema=HarnessContext)
    builder.add_node("supervisor_plan", build_supervisor_plan_node(max_researchers))
    builder.add_node("researcher", build_researcher_node(topic_graph))
    builder.add_node("aggregate", aggregate_node)
    builder.add_node("supervisor_evaluate", supervisor_evaluate_node)
    builder.add_node("follow_up", build_follow_up_node(max_researchers))
    builder.add_node("finalize", build_finalize_node(max_follow_ups))
    builder.add_edge(START, "supervisor_plan")
    builder.add_conditional_edges("supervisor_plan", route_researchers)
    builder.add_edge("researcher", "aggregate")
    builder.add_edge("aggregate", "supervisor_evaluate")
    builder.add_conditional_edges(
        "supervisor_evaluate", build_route_after_evaluate(max_follow_ups)
    )
    builder.add_conditional_edges("follow_up", route_after_follow_up)
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
