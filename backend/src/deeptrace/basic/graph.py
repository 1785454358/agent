"""The exact three-node LangGraph topology for Basic research."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from deeptrace.basic.state import GraphState


def _service(config: RunnableConfig) -> Any:
    service = config.get("configurable", {}).get("service")
    if service is None:
        raise RuntimeError("LangGraph 缺少 ResearchWorkflowNodes 运行服务")
    return service


async def _plan_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).plan_node(state)


async def _parallel_research_node(
    state: GraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).parallel_research_node(state)


async def _writer_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).writer_node(state)


def build_research_graph() -> Any:
    """Compile ``START → plan → parallel_research → writer → END``."""
    workflow = StateGraph(GraphState)
    workflow.add_node("plan", _plan_node)
    workflow.add_node("parallel_research", _parallel_research_node)
    workflow.add_node("writer", _writer_node)
    workflow.add_edge(START, "plan")
    workflow.add_edge("plan", "parallel_research")
    workflow.add_edge("parallel_research", "writer")
    workflow.add_edge("writer", END)
    return workflow.compile()
