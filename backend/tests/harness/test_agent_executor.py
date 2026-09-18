from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.agent_executor import (
    WRITE_TODOS_TOOL,
    build_research_agent_graph,
)
from strategies.fixtures import build_gateway_fixture


class ScriptedModelGateway:
    """Returns queued assistant messages; records whether tools were bound."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def invoke(
        self,
        *,
        role: str,
        messages: list[Any],
        tools: Any | None = None,
    ) -> Any:
        self.calls.append({"role": role, "tools": tools})
        if not self._responses:
            raise AssertionError("scripted model ran out of responses")
        return self._responses.pop(0)


def _tool_call(name: str, arguments: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": arguments, "id": call_id}],
    )


def _topic_input(query: str = "LangGraph harness") -> ResearchTopicInput:
    return ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query=query,
        mode=ResearchMode.WORKFLOW,
        caller_id="workflow-graph",
    )


async def _run(graph, fixture, topic_input: ResearchTopicInput):
    return await graph.ainvoke(
        {"topic_input": topic_input}, context=fixture.context
    )


@pytest.mark.asyncio
async def test_agent_executor_searches_fetches_and_collects_evidence() -> None:
    model = ScriptedModelGateway(
        [
            _tool_call("search_web", {"query": "LangGraph"}, "call-1"),
            _tool_call(
                "fetch_page", {"url": "https://example.com/a"}, "call-2"
            ),
            AIMessage(content="资料已足够。"),
        ]
    )
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "body-a is long enough to be usable"},
        model_gateway=model,
    )
    graph = build_research_agent_graph()

    raw = await _run(graph, fixture, _topic_input())
    outcome = raw["outcome"]

    assert outcome.evidence_ids == [
        await fixture.evidence_id_for("https://example.com/a")
    ]
    assert outcome.attempted_urls == ["https://example.com/a"]
    assert outcome.errors == []
    # every model call in the loop binds the governed research tools
    assert all(call["tools"] for call in model.calls)


@pytest.mark.asyncio
async def test_agent_recovers_after_an_unauthorized_fetch_error() -> None:
    model = ScriptedModelGateway(
        [
            # 1st: model guesses a URL before searching -> not authorized
            _tool_call(
                "fetch_page", {"url": "https://example.com/a"}, "call-1"
            ),
            # 2nd: model repairs by searching first
            _tool_call("search_web", {"query": "LangGraph"}, "call-2"),
            # 3rd: now the URL is observed and may be fetched
            _tool_call(
                "fetch_page", {"url": "https://example.com/a"}, "call-3"
            ),
            AIMessage(content="修复后完成。"),
        ]
    )
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )
    graph = build_research_agent_graph()

    raw = await _run(graph, fixture, _topic_input())
    outcome = raw["outcome"]

    assert outcome.evidence_ids == [
        await fixture.evidence_id_for("https://example.com/a")
    ]
    assert [(error.stage, error.code) for error in outcome.errors] == [
        ("fetch", "url_not_authorized")
    ]


@pytest.mark.asyncio
async def test_agent_is_nudged_when_it_stops_without_evidence() -> None:
    model = ScriptedModelGateway(
        [
            # model tries to answer from memory without calling any tool
            AIMessage(content="我知道答案，不需要工具。"),
            _tool_call("search_web", {"query": "LangGraph"}, "call-1"),
            _tool_call(
                "fetch_page", {"url": "https://example.com/a"}, "call-2"
            ),
            AIMessage(content="现在有证据了。"),
        ]
    )
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )
    graph = build_research_agent_graph()

    raw = await _run(graph, fixture, _topic_input())
    outcome = raw["outcome"]

    assert outcome.evidence_ids == [
        await fixture.evidence_id_for("https://example.com/a")
    ]
    # the model was reminded once before it agreed to use tools
    assert len(model.calls) == 4


@pytest.mark.asyncio
async def test_agent_executor_stops_at_the_iteration_cap() -> None:
    model = ScriptedModelGateway(
        [
            _tool_call("search_web", {"query": f"q{index}"}, f"call-{index}")
            for index in range(10)
        ]
    )
    fixture = build_gateway_fixture(
        default_search_results=[],
        model_gateway=model,
    )
    graph = build_research_agent_graph(max_iterations=2)

    raw = await _run(graph, fixture, _topic_input())
    outcome = raw["outcome"]

    # the loop ran at most two model turns and still produced a structured outcome
    assert len(model.calls) == 2
    assert outcome.executed_steps == 2


@pytest.mark.asyncio
async def test_consecutive_error_fuse_finalizes_before_the_cap() -> None:
    model = ScriptedModelGateway(
        [
            _tool_call(
                "fetch_page", {"url": f"https://example.com/{index}"}, f"c-{index}"
            )
            for index in range(10)
        ]
    )
    fixture = build_gateway_fixture(model_gateway=model)
    graph = build_research_agent_graph(
        max_iterations=10, consecutive_error_limit=2
    )

    raw = await _run(graph, fixture, _topic_input())
    outcome = raw["outcome"]

    # two tool cycles trip the fuse without spending another model call
    assert len(model.calls) == 2
    assert len(outcome.errors) == 2
    assert all(
        error.code == "url_not_authorized" for error in outcome.errors
    )


@pytest.mark.asyncio
async def test_write_todos_updates_the_plan_without_touching_the_gateway() -> None:
    model = ScriptedModelGateway(
        [
            _tool_call(
                WRITE_TODOS_TOOL,
                {"todos": [{"content": "收集来源", "status": "pending"}]},
                "call-1",
            ),
            _tool_call("search_web", {"query": "LangGraph"}, "call-2"),
            _tool_call(
                "fetch_page", {"url": "https://example.com/a"}, "call-3"
            ),
            _tool_call(
                WRITE_TODOS_TOOL,
                {"todos": [{"content": "收集来源", "status": "completed"}]},
                "call-4",
            ),
            AIMessage(content="计划完成。"),
        ]
    )
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )
    graph = build_research_agent_graph()

    raw = await _run(graph, fixture, _topic_input())
    outcome = raw["outcome"]

    # planning is a loop-local state mutation, not a governed external call
    assert len(fixture.gateway.calls) == 2
    assert len(model.calls) == 5
    assert outcome.evidence_ids == [
        await fixture.evidence_id_for("https://example.com/a")
    ]
    assert outcome.plan_total == 1
    assert outcome.plan_completed == 1
    assert outcome.unfinished_todos == []
    assert outcome.plan_complete is True


@pytest.mark.asyncio
async def test_open_todos_block_completion_and_trigger_a_nudge() -> None:
    model = ScriptedModelGateway(
        [
            _tool_call(
                WRITE_TODOS_TOOL,
                {"todos": [{"content": "收集来源", "status": "pending"}]},
                "call-1",
            ),
            _tool_call("search_web", {"query": "LangGraph"}, "call-2"),
            _tool_call(
                "fetch_page", {"url": "https://example.com/a"}, "call-3"
            ),
            # stops with evidence but the plan is still open -> not complete
            AIMessage(content="差不多了。"),
            _tool_call(
                WRITE_TODOS_TOOL,
                {"todos": [{"content": "收集来源", "status": "completed"}]},
                "call-4",
            ),
            AIMessage(content="计划完成。"),
        ]
    )
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )
    graph = build_research_agent_graph()

    raw = await _run(graph, fixture, _topic_input())
    outcome = raw["outcome"]

    # the early stop was rejected once, then the model closed the todo
    assert len(model.calls) == 6
    assert outcome.evidence_ids == [
        await fixture.evidence_id_for("https://example.com/a")
    ]


@pytest.mark.asyncio
async def test_completion_nudge_limit_zero_accepts_an_early_stop() -> None:
    model = ScriptedModelGateway(
        [
            _tool_call(
                WRITE_TODOS_TOOL,
                {"todos": [{"content": "收集来源", "status": "pending"}]},
                "call-1",
            ),
            AIMessage(content="我提前结束。"),
        ]
    )
    fixture = build_gateway_fixture(model_gateway=model)
    graph = build_research_agent_graph(completion_nudge_limit=0)

    raw = await _run(graph, fixture, _topic_input())

    assert raw["outcome"].evidence_ids == []
    assert len(model.calls) == 2
    # an accepted early stop still reports the open plan upward
    outcome = raw["outcome"]
    assert outcome.plan_total == 1
    assert outcome.plan_completed == 0
    assert outcome.unfinished_todos == ["收集来源"]
    assert outcome.plan_complete is False
