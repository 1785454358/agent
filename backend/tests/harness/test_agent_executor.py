from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.agent_executor import (
    WRITE_TODOS_TOOL,
    build_research_agent_graph,
)
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.tools.policy import CallerRole, UrlAuthorizationSource


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


def _fetch_batch(*urls: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "fetch_page", "args": {"url": url}, "id": f"fetch-{index}"}
            for index, url in enumerate(urls)
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,caller_id,role",
    [
        (ResearchMode.WORKFLOW, "workflow-graph", CallerRole.WORKFLOW_GRAPH),
        (
            ResearchMode.PLAN_EXECUTE,
            "plan-execute-executor",
            CallerRole.PLAN_EXECUTE_EXECUTOR,
        ),
        (ResearchMode.MULTI_AGENT, "researcher-0", CallerRole.MULTI_AGENT_RESEARCHER),
    ],
)
async def test_research_gateway_preserves_tenant_caller_and_url_authorization(
    mode, caller_id, role
) -> None:
    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway(
            [
                _tool_call("search_web", {"query": "q"}, "search"),
                _fetch_batch("https://example.com/a"),
                AIMessage(content="done"),
            ]
        ),
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
    )
    request = _topic_input().model_copy(update={"mode": mode, "caller_id": caller_id})
    raw = await _run(build_research_agent_graph(), fixture, request)
    assert raw["outcome"].agent_outcome.status == "completed"
    search, fetch = fixture.gateway.calls
    for invocation in (search, fetch):
        assert invocation["tenant_id"] == "workspace-1"
        assert invocation["caller"].caller_id == caller_id
        assert invocation["caller"].mode is mode
        assert invocation["caller"].role is role
    assert search.get("authorization") is None
    assert fetch["authorization"].source is UrlAuthorizationSource.AGENT_DISCOVERED
    assert fetch["authorization"].urls == frozenset({"https://example.com/a"})


@pytest.mark.asyncio
async def test_page_limit_blocks_extra_fetches_requested_by_the_model() -> None:
    urls = [f"https://example.com/{name}" for name in ("a", "b", "c", "d")]
    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway(
            [
                _tool_call("search_web", {"query": "q"}, "search"),
                _fetch_batch(*urls[:3]),
                _tool_call("fetch_page", {"url": urls[3]}, "extra"),
                AIMessage(content="done"),
            ]
        ),
        default_search_results=[
            {"url": url, "title": "page", "snippet": "s"} for url in urls
        ],
    )
    raw = await _run(
        build_research_agent_graph(),
        fixture,
        _topic_input().model_copy(update={"max_pages": 2}),
    )
    assert fixture.fetcher.calls == ["https://example.com/a", "https://example.com/b"]
    assert len(raw["outcome"].evidence_ids) == 2
    assert len(fixture.gateway.calls) == 3
    assert "page_limit" in str(raw["messages"])


@pytest.mark.asyncio
async def test_duplicate_and_private_urls_do_not_duplicate_or_escape_fetching() -> None:
    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway(
            [
                _tool_call("search_web", {"query": "q"}, "search"),
                _fetch_batch(
                    "https://example.com/a",
                    "https://example.com/a",
                    "http://localhost/secret",
                ),
                AIMessage(content="done"),
            ]
        ),
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"},
            {"url": "http://localhost/secret", "title": "unsafe", "snippet": "s"},
        ],
    )
    raw = await _run(build_research_agent_graph(), fixture, _topic_input())
    assert fixture.fetcher.calls == ["https://example.com/a"]
    assert len(raw["outcome"].evidence_ids) == 1
    assert any(
        error.target == "http://localhost/secret" for error in raw["outcome"].errors
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,reason", [("empty", "completed"), ("raise", "tool_error")]
)
async def test_fetch_failure_preserves_successful_sibling_evidence(
    failure, reason
) -> None:
    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway(
            [
                _tool_call("search_web", {"query": "q"}, "search"),
                _fetch_batch("https://example.com/a", "https://example.com/b"),
                AIMessage(content="done"),
            ]
        ),
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"},
            {"url": "https://example.com/b", "title": "B", "snippet": "s"},
        ],
        fetch_failures={"https://example.com/b": failure},
    )
    raw = await _run(build_research_agent_graph(), fixture, _topic_input())
    outcome = raw["outcome"]
    assert outcome.evidence_ids == [
        await fixture.evidence_id_for("https://example.com/a")
    ]
    assert outcome.agent_outcome.stop_reason == reason
    assert [(error.stage, error.code) for error in outcome.errors] == [
        ("fetch", "empty_page" if failure == "empty" else "tool_internal_error")
    ]
    assert fixture.fetcher.calls.count("https://example.com/b") == 1


@pytest.mark.asyncio
async def test_fatal_search_error_stops_without_fetching_or_repeating() -> None:
    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway(
            [_tool_call("search_web", {"query": "q"}, "search")]
        ),
        search_fail=True,
    )
    raw = await _run(build_research_agent_graph(), fixture, _topic_input())
    assert raw["outcome"].agent_outcome.stop_reason == "tool_error"
    assert [(error.stage, error.code) for error in raw["outcome"].errors] == [
        ("search", "tool_internal_error")
    ]
    assert fixture.search.calls == ["q"]
    assert fixture.fetcher.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "results",
    [
        [],
        [
            {
                "url": f"https://example.com/{index}",
                "title": "page",
                "snippet": "s" * 600,
            }
            for index in range(8)
        ],
    ],
)
async def test_empty_or_truncated_search_preview_cannot_authorize_a_guessed_url(
    results,
) -> None:
    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway(
            [
                _tool_call("search_web", {"query": "q", "limit": 8}, "search"),
                _fetch_batch("https://example.com/0"),
            ]
        ),
        default_search_results=results,
    )
    raw = await _run(
        build_research_agent_graph(max_iterations=2), fixture, _topic_input()
    )
    assert fixture.fetcher.calls == []
    assert raw["outcome"].evidence_ids == []
    assert raw["outcome"].errors[0].code == "url_not_authorized"


@pytest.mark.asyncio
async def test_research_checkpoint_keeps_evidence_references_not_page_bodies() -> None:
    import json

    fixture = build_gateway_fixture(
        model_gateway=ScriptedModelGateway(
            [
                _tool_call("search_web", {"query": "q"}, "search"),
                _fetch_batch("https://example.com/a"),
                AIMessage(content="done"),
            ]
        ),
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "unique-research-checkpoint-body-marker"},
    )
    saver = InMemorySaver(serde=create_harness_checkpoint_serializer())
    graph = build_research_agent_graph(checkpointer=saver)
    config = {"configurable": {"thread_id": "reference-only"}}
    await graph.ainvoke(
        {"topic_input": _topic_input()}, config=config, context=fixture.context
    )
    snapshot = await graph.aget_state(config)
    assert "unique-research-checkpoint-body-marker" not in json.dumps(
        snapshot.values, default=str
    )
    outcome = snapshot.values["outcome"]
    assert outcome.query == "LangGraph harness"
    assert len(outcome.evidence_ids) == 1
    body = await fixture.evidence_store.read_body(
        "workspace-1", outcome.evidence_ids[0]
    )
    assert body == "unique-research-checkpoint-body-marker"


async def _run(graph, fixture, topic_input: ResearchTopicInput):
    return await graph.ainvoke({"topic_input": topic_input}, context=fixture.context)


@pytest.mark.asyncio
async def test_agent_executor_searches_fetches_and_collects_evidence() -> None:
    model = ScriptedModelGateway(
        [
            _tool_call("search_web", {"query": "LangGraph"}, "call-1"),
            _tool_call("fetch_page", {"url": "https://example.com/a"}, "call-2"),
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
            _tool_call("fetch_page", {"url": "https://example.com/a"}, "call-1"),
            # 2nd: model repairs by searching first
            _tool_call("search_web", {"query": "LangGraph"}, "call-2"),
            # 3rd: now the URL is observed and may be fetched
            _tool_call("fetch_page", {"url": "https://example.com/a"}, "call-3"),
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
            _tool_call("fetch_page", {"url": "https://example.com/a"}, "call-2"),
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
    graph = build_research_agent_graph(max_iterations=10, consecutive_error_limit=2)

    raw = await _run(graph, fixture, _topic_input())
    outcome = raw["outcome"]

    # two tool cycles trip the fuse without spending another model call
    assert len(model.calls) == 2
    assert len(outcome.errors) == 2
    assert all(error.code == "url_not_authorized" for error in outcome.errors)


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
            _tool_call("fetch_page", {"url": "https://example.com/a"}, "call-3"),
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
            _tool_call("fetch_page", {"url": "https://example.com/a"}, "call-3"),
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
