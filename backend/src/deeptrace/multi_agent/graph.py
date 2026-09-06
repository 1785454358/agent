"""LangGraph topology for Supervisor Plan-and-Execute research."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from deeptrace.multi_agent.state import (
    MultiAgentGraphState,
    route_after_plan,
    route_after_replan,
)


def _service(config: RunnableConfig) -> Any:
    service = config.get("configurable", {}).get("service")
    if service is None:
        raise RuntimeError("LangGraph 缺少 MultiAgentWorkflowNodes 运行服务")
    return service


async def _plan_node(
    state: MultiAgentGraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).plan_node(state)


async def _execute_node(
    state: MultiAgentGraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).execute_node(state)


async def _replan_node(
    state: MultiAgentGraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).replan_node(state)


async def _writer_node(
    state: MultiAgentGraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).writer_node(state)


def build_multi_agent_graph() -> Any:
    """Compile Plan → parallel Execute → Replan loop → Writer."""
    workflow = StateGraph(MultiAgentGraphState)
    workflow.add_node("plan", _plan_node)
    workflow.add_node("execute", _execute_node)
    workflow.add_node("replan", _replan_node)
    workflow.add_node("writer", _writer_node)
    workflow.add_edge(START, "plan")
    workflow.add_conditional_edges(
        "plan",
        route_after_plan,
        {"execute": "execute", "writer": "writer"},
    )
    workflow.add_edge("execute", "replan")
    workflow.add_conditional_edges(
        "replan",
        route_after_replan,
        {"execute": "execute", "writer": "writer"},
    )
    workflow.add_edge("writer", END)
    return workflow.compile()
