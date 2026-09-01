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


async def _tools_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).tools_node(state)


async def _plan_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).plan_node(state)


async def _start_task_node(
    state: GraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).start_task_node(state)


async def _research_node(
    state: GraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).research_node(state)


async def _complete_task_node(
    state: GraphState, config: RunnableConfig
) -> dict[str, Any]:
    return await _service(config).complete_task_node(state)


async def _writer_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    return await _service(config).writer_node(state)


def route_after_agent(state: GraphState) -> Literal["tools", "__end__"]:
    """有工具调用时继续执行，否则结束研究。"""
    if state.get("final_answer"):
        return END
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def route_after_research(
    state: GraphState,
) -> Literal["tools", "complete_task"]:
    """完成协议由节点处理，外部工具调用才进入 executor。"""
    if state.get("pending_task_completion") is not None:
        return "complete_task"
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and last.tool_calls:
        names = {str(call.get("name", "")) for call in last.tool_calls}
        if "complete_research_task" in names:
            return "complete_task"
        if names & {"search_web", "fetch_webpage"}:
            return "tools"
    return "complete_task"


def route_after_task(state: GraphState) -> Literal["start_task", "writer"]:
    """还有未执行任务则继续，否则统一写作。"""
    plan = state.get("research_plan")
    if plan is None or state.get("current_task_index", 0) >= len(plan.tasks):
        return "writer"
    if state.get("force_finalize"):
        return "writer"
    return "start_task"


def build_research_graph() -> Any:
    """构建规划、逐任务研究和统一写作的阶段 3 拓扑。"""
    workflow = StateGraph(GraphState)
    workflow.add_node("plan", _plan_node)
    workflow.add_node("start_task", _start_task_node)
    workflow.add_node("research", _research_node)
    workflow.add_node("tools", _tools_node)
    workflow.add_node("complete_task", _complete_task_node)
    workflow.add_node("writer", _writer_node)
    workflow.add_edge(START, "plan")
    workflow.add_edge("plan", "start_task")
    workflow.add_edge("start_task", "research")
    workflow.add_conditional_edges(
        "research",
        route_after_research,
        {"tools": "tools", "complete_task": "complete_task"},
    )
    workflow.add_edge("tools", "research")
    workflow.add_conditional_edges(
        "complete_task",
        route_after_task,
        {"start_task": "start_task", "writer": "writer"},
    )
    workflow.add_edge("writer", END)
    return workflow.compile()
