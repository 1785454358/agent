"""阶段 2 LangGraph 拓扑，运行依赖通过 config 注入。"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from deeptrace.orchestration.state import GraphState


def _service(config: RunnableConfig) -> Any:
    service = config.get("configurable", {}).get("service")
    if service is None:
        raise RuntimeError("LangGraph 缺少 ResearchNodes 运行服务")
    return service


async def _agent_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).agent_node(state)


async def _plan_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).plan_node(state)


async def _writer_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).writer_node(state)


async def _research_all_node(
    state: GraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).research_all_node(state)


def route_after_agent(state: GraphState) -> Literal["tools", "__end__"]:
    """有工具调用时继续执行，否则结束研究。"""
    if state.get("final_answer"):
        return END
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def build_research_graph() -> Any:
    """构建规划、并行研究与统一写作的拓扑。"""
    workflow = StateGraph(GraphState)
    workflow.add_node("plan", _plan_node)
    workflow.add_node("research_all", _research_all_node)
    workflow.add_node("writer", _writer_node)
    workflow.add_edge(START, "plan")
    workflow.add_edge("plan", "research_all")
    workflow.add_edge("research_all", "writer")
    workflow.add_edge("writer", END)
    return workflow.compile()
