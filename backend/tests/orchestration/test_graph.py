import json
from datetime import date
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langgraph.graph import END

from deeptrace.models import TaskCompletion
from deeptrace.orchestration import (
    build_research_graph,
    route_after_agent,
    route_after_research,
    route_after_task,
    route_after_task_completion,
    route_after_tools,
    route_after_verification,
    ToolCallResult,
    build_unverified_finalization,
    build_tool_messages,
    select_agent_model_mode,
)
from deeptrace.prompts.research import build_system_prompt


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
    assert {
        "plan",
        "start_task",
        "research",
        "tools",
        "complete_task",
        "evidence_ingest",
        "claim_extract",
        "verify",
        "start_verification_research",
        "verification_research",
        "finalize_task",
        "writer",
    }.issubset(graph.get_graph().nodes)

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
    assert route_after_research(
        {"messages": [tool_message], "pending_task_completion": None}
    ) == "tools"
    completion = AIMessage(
        content="",
        tool_calls=[{
            "id": "done-1",
            "name": "complete_research_task",
            "args": {
                "task_id": "task-01",
                "summary": "完成",
                "covered_topics": [],
                "unresolved_topics": [],
            },
            "type": "tool_call",
        }],
    )
    assert route_after_research(
        {"messages": [completion], "pending_task_completion": None}
    ) == "complete_task"
    assert route_after_research({
        "messages": [],
        "pending_task_completion": TaskCompletion(
            task_id="task-01", summary="预算结束"
        ),
    }) == "complete_task"
    assert route_after_task(
        {"research_plan": None, "current_task_index": 0}
    ) == "writer"


def test_task_completion_and_verification_routes_are_bounded() -> None:
    assert route_after_task_completion({}) == "evidence_ingest"
    assert route_after_verification(
        {
            "verification_mode": "initial",
            "verification_gaps": {
                "gap-01": SimpleNamespace(priority="high")
            },
        }
    ) == "start_verification_research"
    assert route_after_verification(
        {
            "verification_mode": "supplement",
            "verification_gaps": {
                "gap-01": SimpleNamespace(priority="high")
            },
        }
    ) == "finalize_task"
    assert route_after_tools(
        {"verification_mode": "supplement"}
    ) == "verification_research"


def test_budget_selects_final_model_only_when_research_should_end() -> None:
    assert select_agent_model_mode(
        step=8,
        soft_max_steps=8,
        hard_max_steps=12,
        extension_granted=False,
        can_extend=False,
        has_notes=False,
    ) == "refuse"
    refusal = build_unverified_finalization(step=8)
    assert refusal["termination_reason"] == "no_verified_sources"
    assert "未在预算内获得成功抓取的研究笔记" in refusal["final_answer"]
    assert "不能把搜索摘要当事实" in refusal["final_answer"]

    assert select_agent_model_mode(
        step=8,
        soft_max_steps=8,
        hard_max_steps=12,
        extension_granted=False,
        can_extend=False,
        has_notes=True,
    ) == "finalize"
    assert select_agent_model_mode(
        step=7,
        soft_max_steps=8,
        hard_max_steps=12,
        extension_granted=False,
        can_extend=False,
        has_notes=False,
    ) == "agent"


def test_system_prompt_grounds_relative_time_in_current_date() -> None:
    prompt = build_system_prompt(date(2026, 8, 31))

    assert "2026-08-31" in prompt
    assert "今天/最新/今年" in prompt
    assert "搜索词" in prompt
    assert "发布日期" in prompt
