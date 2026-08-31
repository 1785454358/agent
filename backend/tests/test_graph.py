import json

from langchain_core.messages import AIMessage
from langgraph.graph import END

from deeptrace.graph import build_research_graph, route_after_agent
from deeptrace.nodes import (
    ToolCallResult,
    build_tool_messages,
    select_agent_model_mode,
)


def test_tool_messages_follow_original_calls_when_results_finish_out_of_order() -> None:
    """并发任务的完成顺序不能改变 tool_call_id 与结果的对应关系。"""
    calls = [
        {"id": "call-a", "name": "fetch_webpage", "args": {"url": "https://a"}},
        {"id": "call-b", "name": "fetch_webpage", "args": {"url": "https://b"}},
    ]
    results = [
        ToolCallResult("call-b", 1, {"ok": True, "title": "B"}),
        ToolCallResult("call-a", 0, {"ok": True, "title": "A"}),
    ]

    messages = build_tool_messages(calls, results)

    assert [message.tool_call_id for message in messages] == ["call-a", "call-b"]
    assert [json.loads(message.content)["title"] for message in messages] == ["A", "B"]


def test_graph_compiles_and_router_distinguishes_tools_from_completion() -> None:
    graph = build_research_graph()
    assert {"agent", "tools"}.issubset(graph.get_graph().nodes)

    tool_message = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-search",
                "name": "search_web",
                "args": {"query": "Agent 新闻"},
                "type": "tool_call",
            }
        ],
    )
    assert route_after_agent({"messages": [tool_message], "final_answer": ""}) == "tools"
    assert route_after_agent({"messages": [], "final_answer": "已完成"}) == END


def test_budget_selects_final_model_only_when_research_should_end() -> None:
    assert select_agent_model_mode(
        step=8,
        soft_max_steps=8,
        hard_max_steps=12,
        extension_granted=False,
        can_extend=False,
    ) == "finalize"
    assert select_agent_model_mode(
        step=7,
        soft_max_steps=8,
        hard_max_steps=12,
        extension_granted=False,
        can_extend=False,
    ) == "agent"
