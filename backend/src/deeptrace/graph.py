"""阶段 2 LangGraph 拓扑，运行依赖通过 config 注入。"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from deeptrace.state import GraphState


def _service(config: RunnableConfig) -> Any:
    service = config.get("configurable", {}).get("service")
    if service is None:
        raise RuntimeError("LangGraph 缺少 ResearchNodes 运行服务")
    return service


async def _agent_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).agent_node(state)


async def _tools_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).tools_node(state)


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
    """构建并编译固定的 agent → tools → agent 闭环。"""
    workflow = StateGraph(GraphState)
    workflow.add_node("agent", _agent_node)
    workflow.add_node("tools", _tools_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", route_after_agent)
    workflow.add_edge("tools", "agent")
    return workflow.compile()
