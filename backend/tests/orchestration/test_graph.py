import json
from datetime import date
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langgraph.graph import END

from deeptrace.orchestration import (
    build_research_graph,
    route_after_agent,
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


def test_graph_compiles_with_parallel_pipeline() -> None:
    graph = build_research_graph()
    assert {"plan", "research_all", "writer"}.issubset(
        graph.get_graph().nodes
    )


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
