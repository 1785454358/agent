"""Tool-call orchestration without research state or completion semantics."""

from collections.abc import Callable
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph


@dataclass(frozen=True)
class LoopNodes:
    prepare_context: Callable
    call_model: Callable
    execute_tools: Callable
    observe: Callable
    nudge: Callable
    finalize: Callable


def build_tool_call_loop(
    *,
    state_schema,
    nodes: LoopNodes,
    context_schema=None,
    max_iterations=8,
    checkpointer=None,
):
    """The domain owns context, tools and completion; the loop owns routing.

    State exposes messages and stop_reason. prepare_context enforces its domain
    iteration bound; the graph also has a recursion ceiling as a final guard.
    Tool effects and observation are separate checkpoint boundaries.
    """
    if max_iterations < 1:
        raise ValueError("max_iterations must be positive")

    def route_model(state):
        if state.get("stop_reason"):
            return "finalize"
        return "execute_tools" if state["messages"][-1].tool_calls else "observe"

    def route_observation(state):
        if state.get("stop_reason"):
            return "finalize"
        return "nudge" if state["messages"][-1].type == "ai" else "prepare_context"

    builder = StateGraph(state_schema, context_schema=context_schema)
    for name in (
        "prepare_context",
        "call_model",
        "execute_tools",
        "observe",
        "nudge",
        "finalize",
    ):
        builder.add_node(name, getattr(nodes, name))
    builder.add_edge(START, "prepare_context")
    builder.add_conditional_edges(
        "prepare_context",
        lambda state: "finalize" if state.get("stop_reason") else "call_model",
    )
    builder.add_conditional_edges("call_model", route_model)
    builder.add_edge("execute_tools", "observe")
    builder.add_conditional_edges("observe", route_observation)
    builder.add_edge("nudge", "prepare_context")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer).with_config(
        {"recursion_limit": max_iterations * 5 + 10}
    )
