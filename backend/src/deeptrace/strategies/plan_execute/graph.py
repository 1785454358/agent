"""Compilation of the Plan-and-Execute research strategy subgraph."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.plan_execute.nodes import (
    build_execute_task_node,
    build_finalize_node,
    build_plan_node,
    build_replan_node,
    build_route_after_evaluate,
    evaluate_node,
    route_after_replan,
    route_after_select,
    select_task_node,
)
from deeptrace.strategies.plan_execute.state import PlanExecuteState


def build_plan_execute_research_graph(
    topic_graph,
    *,
    max_tasks: int = 6,
    max_replans: int = 2,
    checkpointer=None,
) -> CompiledStateGraph:
    builder = StateGraph(PlanExecuteState, context_schema=HarnessContext)
    builder.add_node("plan", build_plan_node(max_tasks))
    builder.add_node("select_task", select_task_node)
    builder.add_node("execute_task", build_execute_task_node(topic_graph))
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("replan", build_replan_node(max_tasks))
    builder.add_node("finalize", build_finalize_node(max_replans))
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "select_task")
    builder.add_conditional_edges("select_task", route_after_select)
    builder.add_edge("execute_task", "select_task")
    builder.add_conditional_edges(
        "evaluate", build_route_after_evaluate(max_replans)
    )
    builder.add_conditional_edges("replan", route_after_replan)
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
