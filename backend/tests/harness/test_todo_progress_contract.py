"""Progress-update instructions and existing batch/exit boundaries stay aligned."""

import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput, ToolResult
from deeptrace.domain.errors import classify_error_code
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer

URL = "https://example.com/progress"
BODY = "Checkpoints persist state at each super-step boundary."
CALLERS = {
    ResearchMode.WORKFLOW: "workflow-graph",
    ResearchMode.PLAN_EXECUTE: "plan-execute-executor",
    ResearchMode.MULTI_AGENT: "researcher-0",
}


def topic(mode):
    return ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="checkpoint boundary",
        mode=mode,
        caller_id=CALLERS[mode],
        original_task="Explain checkpoint boundaries",
        constraints=["only official sources"],
    )


def call(name, args, identity):
    return {"name": name, "args": args, "id": identity}


def todo_call(search_status, read_status, identity):
    return call(
        "write_todos",
        {
            "todos": [
                {"content": "Discover source", "status": search_status},
                {"content": "Read source", "status": read_status},
            ]
        },
        identity,
    )


def assert_pairs(messages):
    requested = [c["id"] for m in messages for c in getattr(m, "tool_calls", [])]
    returned = [m.tool_call_id for m in messages if isinstance(m, ToolMessage)]
    assert len(requested) == len(set(requested))
    assert sorted(requested) == sorted(returned)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("surface", ["system", "tool"])
async def test_shared_node_delivers_observed_progress_update_contract(mode, surface):
    class CaptureGateway:
        delivered = None

        async def invoke(self, *, role, messages, tools=None):
            assert role == "researcher"
            if surface == "system":
                self.delivered = str(messages[0].content)
            else:
                self.delivered = next(
                    tool["function"]["description"]
                    for tool in tools
                    if tool["function"]["name"] == "write_todos"
                )
            assert "Explain checkpoint boundaries" in str(messages[1].content)
            assert "only official sources" in str(messages[1].content)
            return AIMessage(
                content="", tool_calls=[todo_call("pending", "pending", "p")]
            )

    gateway = CaptureGateway()
    fixture = build_gateway_fixture(model_gateway=gateway)
    raw = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": topic(mode)}, context=fixture.context
    )

    assert raw["outcome"].agent_outcome.stop_reason == "iteration_limit"
    assert raw["outcome"].unfinished_todos == ["Discover source", "Read source"]
    assert "后续每轮" not in gateway.delivered
    for rule in ("仅在", "已观察到", "计划", "变化", "同批", "尚未返回", "不能"):
        assert rule in gateway.delivered


class ProgressGateway:
    """Only the external model is scripted; decisions read actual tool outputs."""

    async def invoke(self, *, role, messages, tools=None):
        assert role == "researcher" and tools
        observations = [
            json.loads(m.content) for m in messages if isinstance(m, ToolMessage)
        ]
        if not observations:
            calls = [
                todo_call("in_progress", "pending", "init"),
                call("search_web", {"query": "checkpoint boundary"}, "search"),
            ]
        else:
            last = observations[-1]
            assert last["ok"]
            if last["tool"] == "search_web":
                url = json.loads(last["preview"])["results"][0]["url"]
                calls = [
                    todo_call("completed", "in_progress", "discovered"),
                    call("fetch_page", {"url": url}, "fetch"),
                ]
            elif last["tool"] == "fetch_page":
                calls = [
                    call(
                        "read_evidence",
                        {"evidence_id": last["evidence_ids"][0]},
                        "read",
                    )
                ]
            elif last["tool"] == "read_evidence":
                calls = [todo_call("completed", "completed", "read-done")]
            else:
                assert last["tool"] == "write_todos" and last["completed"] == 2
                return AIMessage(content="Observed source read; research finished.")
        return AIMessage(content="", tool_calls=calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_progress_batches_resume_without_repeating_external_effects(mode):
    fixture = build_gateway_fixture(
        model_gateway=ProgressGateway(),
        default_search_results=[
            {"url": URL, "title": "Progress", "snippet": "boundary"}
        ],
        pages={URL: BODY},
    )
    saver = InMemorySaver(serde=create_harness_checkpoint_serializer())
    config = {"configurable": {"thread_id": f"progress-{mode.value}"}}
    graph = build_research_agent_graph(max_iterations=8, checkpointer=saver)
    paused = await graph.ainvoke(
        {"topic_input": topic(mode)},
        config=config,
        context=fixture.context,
        interrupt_after=["execute_tools"],
    )
    assert fixture.search.calls == ["checkpoint boundary"]
    assert fixture.fetcher.calls == []
    assert [t.status.value for t in paused["todos"]] == ["in_progress", "pending"]
    rebuilt = build_research_agent_graph(max_iterations=8, checkpointer=saver)
    raw = await rebuilt.ainvoke(None, config=config, context=fixture.context)

    assert fixture.search.calls == ["checkpoint boundary"]
    assert fixture.fetcher.calls == [URL]
    outcome = raw["outcome"].agent_outcome
    assert outcome.status == "completed" and outcome.iterations == 5
    assert outcome.plan_total == outcome.plan_completed == 2
    assert outcome.unfinished_todos == []
    assert len(outcome.evidence_ids) == 1
    assert (
        await fixture.evidence_store.read_body(
            fixture.context.workspace_id, outcome.evidence_ids[0]
        )
        == BODY
    )
    assert [c["request"].tool.value for c in fixture.gateway.calls] == [
        "search_web",
        "fetch_page",
        "read_evidence",
    ]
    read_message = next(
        message
        for message in raw["messages"]
        if isinstance(message, ToolMessage) and message.tool_call_id == "read"
    )
    view = json.loads(json.loads(read_message.content)["preview"])
    assert view["evidence_id"] == outcome.evidence_ids[0]
    assert view["passages"]
    for passage in view["passages"]:
        assert BODY[passage["start"] : passage["end"]] == passage["text"]
    assert_pairs(raw["messages"])
    checkpoint = await rebuilt.aget_state(config)
    assert checkpoint.values["outcome"] == raw["outcome"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_source", [True, False])
async def test_completion_still_requires_evidence_and_no_open_todos(with_source):
    class FinishGateway:
        first = True

        async def invoke(self, *, role, messages, tools=None):
            if self.first:
                self.first = False
                return AIMessage(
                    content="",
                    tool_calls=[
                        todo_call(
                            "completed", "pending" if with_source else "completed", "p"
                        )
                    ],
                )
            return AIMessage(content="done")

    fixture = build_gateway_fixture(model_gateway=FinishGateway(), pages={URL: BODY})
    evidence = []
    if with_source:
        from deeptrace.tools.evidence_store import EvidenceDraft

        record = await fixture.evidence_store.ingest(
            fixture.context.workspace_id,
            EvidenceDraft(
                canonical_url=URL,
                title="Progress",
                media_type="text/plain",
                body=BODY,
                fetched_at=fixture.context.clock.now(),
                source_quality=1.0,
            ),
        )
        evidence = [record.id]
    raw = await build_research_agent_graph(completion_nudge_limit=0).ainvoke(
        {"topic_input": topic(ResearchMode.WORKFLOW), "evidence_ids": evidence},
        context=fixture.context,
    )
    assert raw["outcome"].agent_outcome.status == "partial"
    assert raw["outcome"].agent_outcome.stop_reason == "incomplete_plan"
    assert raw["outcome"].unfinished_todos == (["Read source"] if with_source else [])
    assert_pairs(raw["messages"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,reason",
    [("budget_exhausted", "budget_exhausted"), ("tool_internal_error", "tool_error")],
)
async def test_completed_todo_declarations_do_not_erase_strong_tool_exit(code, reason):
    class Model:
        async def invoke(self, *, role, messages, tools=None):
            return AIMessage(
                content="",
                tool_calls=[
                    todo_call("completed", "completed", "p"),
                    call("search_web", {"query": "q"}, "search"),
                    call("search_web", {"query": "other"}, "other"),
                ],
            )

    fixture = build_gateway_fixture(model_gateway=Model())

    class FailedToolGateway:
        async def execute(self, **kwargs):
            request = kwargs["request"]
            return ToolResult(
                request_id=request.request_id,
                run_id=request.run_id,
                thread_id=request.thread_id,
                call_id=request.call_id,
                tool=request.tool,
                ok=False,
                error_code=code,
                error_category=classify_error_code(code),
            )

    raw = await build_research_agent_graph(max_tool_concurrency=1).ainvoke(
        {"topic_input": topic(ResearchMode.WORKFLOW)},
        context=replace(fixture.context, tool_gateway=FailedToolGateway()),
    )
    assert raw["outcome"].agent_outcome.status != "completed"
    assert raw["outcome"].agent_outcome.stop_reason == reason
    assert raw["outcome"].agent_outcome.errors
    assert_pairs(raw["messages"])
