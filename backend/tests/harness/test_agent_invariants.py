from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from strategies.fixtures import build_gateway_fixture


class Model:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def invoke(self, *, role, messages, tools=None):
        self.calls.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def call(name, args, identity):
    return {"name": name, "args": args, "id": identity}


def task(**kwargs):
    return ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="branch task",
        mode=ResearchMode.WORKFLOW,
        caller_id="workflow-graph",
        **kwargs,
    )


def assert_pairs(messages):
    requested = [c["id"] for m in messages for c in getattr(m, "tool_calls", [])]
    returned = [m.tool_call_id for m in messages if isinstance(m, ToolMessage)]
    assert sorted(requested) == sorted(returned)


@pytest.mark.asyncio
async def test_context_survives_every_model_turn():
    model = Model(
        AIMessage(content="", tool_calls=[call("search_web", {"query": "q"}, "one")]),
        AIMessage(content="done"),
    )
    fixture = build_gateway_fixture(model_gateway=model)
    raw = await build_research_agent_graph(max_iterations=2).ainvoke(
        {"topic_input": task()}, context=fixture.context
    )
    for messages in model.calls:
        assert any(m.type == "system" for m in messages)
        assert any("branch task" in str(m.content) for m in messages)
    assert_pairs(raw["messages"])
    assert raw["outcome"].agent_outcome.stop_reason == "iteration_limit"


@pytest.mark.asyncio
async def test_original_task_and_constraints_are_pinned():
    model = Model(AIMessage(content="done"))
    fixture = build_gateway_fixture(model_gateway=model)
    raw = await build_research_agent_graph(completion_nudge_limit=0).ainvoke(
        {
            "topic_input": task(
                original_task="original question", constraints=["only official sources"]
            )
        },
        context=fixture.context,
    )
    text = "\n".join(str(m.content) for m in model.calls[0])
    assert "original question" in text and "only official sources" in text
    assert raw["outcome"].agent_outcome.status == "partial"


@pytest.mark.asyncio
async def test_last_iteration_tool_batch_is_closed():
    model = Model(
        AIMessage(content="", tool_calls=[call("search_web", {"query": "q"}, "one")])
    )
    fixture = build_gateway_fixture(model_gateway=model)
    raw = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": task()}, context=fixture.context
    )
    assert_pairs(raw["messages"])
    assert len(fixture.gateway.calls) == 1
    assert raw["outcome"].agent_outcome.iterations == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,reason,status",
    [
        (RuntimeError("private secret"), "model_error", "failed"),
        (asyncio.CancelledError(), "cancelled", "cancelled"),
    ],
)
async def test_model_failure_and_cancel_produce_outcome(error, reason, status):
    fixture = build_gateway_fixture(model_gateway=Model(error))
    raw = await build_research_agent_graph().ainvoke(
        {"topic_input": task()}, context=fixture.context
    )
    outcome = raw["outcome"].agent_outcome
    assert outcome.stop_reason == reason and outcome.status == status
    assert "private secret" not in outcome.model_dump_json()


@pytest.mark.asyncio
async def test_independent_tools_overlap_and_merge_in_call_order():
    model = Model(
        AIMessage(
            content="",
            tool_calls=[
                call("search_web", {"query": "a"}, "a"),
                call("search_web", {"query": "b"}, "b"),
            ],
        )
    )
    fixture = build_gateway_fixture(model_gateway=model)
    started = set()
    both_started = asyncio.Event()
    inner = fixture.gateway

    class BarrierGateway:
        async def execute(self, **kwargs):
            started.add(kwargs["request"].call_id)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), 1)
            return await inner.execute(**kwargs)

    raw = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": task()},
        context=replace(fixture.context, tool_gateway=BarrierGateway()),
    )
    assert len(inner.calls) == 2
    assert [m.tool_call_id for m in raw["messages"] if isinstance(m, ToolMessage)] == [
        "a",
        "b",
    ]
    assert_pairs(raw["messages"])


@pytest.mark.asyncio
async def test_checkpoint_resume_after_model_keeps_context_and_closes_calls():
    saver = InMemorySaver(serde=create_harness_checkpoint_serializer())
    first = Model(
        AIMessage(content="", tool_calls=[call("search_web", {"query": "a"}, "a")])
    )
    fixture = build_gateway_fixture(model_gateway=first)
    config = {"configurable": {"thread_id": "resume-thread"}}
    graph = build_research_agent_graph(max_iterations=2, checkpointer=saver)
    await graph.ainvoke(
        {"topic_input": task()},
        config=config,
        context=fixture.context,
        interrupt_after=["call_model"],
    )
    second = Model(AIMessage(content="done"))
    rebuilt = build_research_agent_graph(max_iterations=2, checkpointer=saver)
    raw = await rebuilt.ainvoke(
        None, config=config, context=replace(fixture.context, model_gateway=second)
    )
    assert_pairs(raw["messages"])
    assert len(fixture.gateway.calls) == 1
    assert any(m.type == "system" for m in second.calls[0])
    assert any("branch task" in str(m.content) for m in second.calls[0])
    assert raw["outcome"].agent_outcome is not None


@pytest.mark.asyncio
async def test_search_then_dependent_fetch_in_one_batch():
    model = Model(
        AIMessage(
            content="",
            tool_calls=[
                call("search_web", {"query": "a"}, "a"),
                call("fetch_page", {"url": "https://example.com/a"}, "b"),
            ],
        )
    )
    fixture = build_gateway_fixture(
        model_gateway=model,
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
    )
    raw = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": task()}, context=fixture.context
    )
    assert raw["outcome"].evidence_ids
    assert_pairs(raw["messages"])


@pytest.mark.asyncio
async def test_checkpoint_after_tools_does_not_repeat_external_call():
    saver = InMemorySaver(serde=create_harness_checkpoint_serializer())
    fixture = build_gateway_fixture(
        model_gateway=Model(
            AIMessage(content="", tool_calls=[call("search_web", {"query": "a"}, "a")])
        )
    )
    config = {"configurable": {"thread_id": "after-tools"}}
    graph = build_research_agent_graph(max_iterations=2, checkpointer=saver)
    await graph.ainvoke(
        {"topic_input": task(original_task="original", constraints=["constraint"])},
        config=config,
        context=fixture.context,
        interrupt_after=["execute_tools"],
    )
    second = Model(AIMessage(content="done"))
    raw = await build_research_agent_graph(
        max_iterations=2, checkpointer=saver
    ).ainvoke(
        None, config=config, context=replace(fixture.context, model_gateway=second)
    )
    assert len(fixture.gateway.calls) == 1
    text = str(second.calls[0])
    assert "original" in text and "constraint" in text
    assert_pairs(raw["messages"])


@pytest.mark.asyncio
async def test_tool_cancellation_closes_entire_batch():
    fixture = build_gateway_fixture(
        model_gateway=Model(
            AIMessage(
                content="",
                tool_calls=[
                    call("search_web", {"query": "a"}, "a"),
                    call("search_web", {"query": "b"}, "b"),
                ],
            )
        )
    )

    class CancelGateway:
        async def execute(self, **kwargs):
            raise asyncio.CancelledError()

    raw = await build_research_agent_graph().ainvoke(
        {"topic_input": task()},
        context=replace(fixture.context, tool_gateway=CancelGateway()),
    )
    assert raw["outcome"].agent_outcome.status == "cancelled"
    assert_pairs(raw["messages"])


@pytest.mark.asyncio
async def test_context_overflow_produces_outcome_without_model_call():
    from deeptrace.harness.token_budget import TokenBudgetConfig

    model = Model()
    fixture = build_gateway_fixture(model_gateway=model)
    raw = await build_research_agent_graph(
        token_budget=TokenBudgetConfig(context_tokens=10)
    ).ainvoke({"topic_input": task()}, context=fixture.context)
    assert raw["outcome"].agent_outcome.stop_reason == "context_limit"
    assert model.calls == []


def test_context_trims_complete_exchanges_without_mutating_history():
    from deeptrace.harness.policies.agent_context import (
        message_tokens,
        prepare_messages,
    )
    from deeptrace.harness.token_budget import TokenBudgetConfig

    history = [
        AIMessage(content="", tool_calls=[call("search_web", {"query": "old"}, "old")]),
        ToolMessage(content="large old text " * 1000, tool_call_id="old"),
        AIMessage(content="", tool_calls=[call("search_web", {"query": "new"}, "new")]),
        ToolMessage(content="recent result", tool_call_id="new"),
    ]
    state = {"topic_input": task(), "messages": history}
    recent_view = prepare_messages(
        {**state, "messages": history[-2:]}, [], TokenBudgetConfig()
    )
    config = TokenBudgetConfig(
        context_tokens=message_tokens(recent_view) + 10,
        output_reserve_tokens=0,
        safety_tokens=0,
    )
    view = prepare_messages(state, [], config)
    assert_pairs(view)
    assert [m.tool_call_id for m in view if isinstance(m, ToolMessage)] == ["new"]
    assert len(history) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_every_strategy_model_call_has_system_original_task_and_constraints(mode):
    import json

    from deeptrace.strategies.multi_agent.graph import build_multi_agent_research_graph
    from deeptrace.strategies.plan_execute.graph import (
        build_plan_execute_research_graph,
    )
    from deeptrace.strategies.workflow.graph import build_workflow_research_graph

    roles = []

    class AllRoles:
        def __init__(self):
            self.research_turn = 0

        async def invoke(self, *, role, messages, tools=None):
            roles.append(role)
            assert any(m.type == "system" for m in messages)
            text = "\n".join(str(m.content) for m in messages)
            assert "original task" in text and "current constraint" in text
            if role == "researcher":
                self.research_turn += 1
                if self.research_turn == 1:
                    return AIMessage(
                        content="",
                        tool_calls=[call("search_web", {"query": "branch"}, "search")],
                    )
                if self.research_turn == 2:
                    return AIMessage(
                        content="",
                        tool_calls=[
                            call(
                                "fetch_page", {"url": "https://example.com/a"}, "fetch"
                            )
                        ],
                    )
                return AIMessage(content="done")
            if role == "evaluator":
                payload = {"findings": [], "unresolved_gaps": []}
                payload.update(
                    {"sufficient": True}
                    if mode == ResearchMode.WORKFLOW
                    else {"action": "complete", "reason": "done"}
                )
                return json.dumps(payload)
            return json.dumps(
                {
                    "assignments" if mode == ResearchMode.MULTI_AGENT else "queries": [
                        "branch"
                    ]
                }
            )

    fixture = build_gateway_fixture(
        model_gateway=AllRoles(),
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
    )
    factories = {
        ResearchMode.WORKFLOW: build_workflow_research_graph,
        ResearchMode.PLAN_EXECUTE: build_plan_execute_research_graph,
        ResearchMode.MULTI_AGENT: build_multi_agent_research_graph,
    }
    graph = factories[mode](build_research_agent_graph())
    result = await graph.ainvoke(
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "question": "original task",
            "conversation_summary": {"user_constraints": ["current constraint"]},
            "current_date": "2026-09-18",
            "timezone": "UTC",
        },
        context=fixture.context,
    )
    assert "researcher" in roles and "evaluator" in roles
    assert result["outcome"].termination_reason == "completed"
    assert len(fixture.gateway.calls) == 2


@pytest.mark.asyncio
async def test_replay_after_tool_commit_uses_ledger_instead_of_provider():
    saver = InMemorySaver(serde=create_harness_checkpoint_serializer())
    fixture = build_gateway_fixture(
        model_gateway=Model(
            AIMessage(content="", tool_calls=[call("search_web", {"query": "a"}, "a")])
        )
    )
    config = {"configurable": {"thread_id": "ledger-replay"}}
    graph = build_research_agent_graph(max_iterations=1, checkpointer=saver)
    await graph.ainvoke(
        {"topic_input": task()},
        config=config,
        context=fixture.context,
        interrupt_after=["call_model"],
    )
    before_tool = await graph.aget_state(config)
    await graph.ainvoke(None, config=config, context=fixture.context)
    replay = await graph.ainvoke(
        None, config=before_tool.config, context=fixture.context
    )
    assert_pairs(replay["messages"])
    assert len(fixture.search.calls) == 1
    assert replay["outcome"].agent_outcome.stop_reason == "iteration_limit"


@pytest.mark.asyncio
async def test_call_ids_are_scoped_to_branch_for_ledger():
    fixture = build_gateway_fixture()
    for query in ("branch a", "branch b"):
        model = Model(
            AIMessage(
                content="", tool_calls=[call("search_web", {"query": query}, "same-id")]
            )
        )
        raw = await build_research_agent_graph(max_iterations=1).ainvoke(
            {"topic_input": task().model_copy(update={"query": query})},
            context=replace(fixture.context, model_gateway=model),
        )
        assert raw["outcome"].agent_outcome.stop_reason == "iteration_limit"
        assert_pairs(raw["messages"])
    assert fixture.search.calls == ["branch a", "branch b"]


@pytest.mark.asyncio
async def test_invalid_tool_arguments_receive_a_paired_error():
    model = Model(
        AIMessage(
            content="",
            invalid_tool_calls=[
                {
                    "name": "search_web",
                    "args": "{broken",
                    "id": "bad",
                    "error": "invalid json",
                }
            ],
        )
    )
    fixture = build_gateway_fixture(model_gateway=model)
    raw = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": task()}, context=fixture.context
    )
    returned = [m for m in raw.get("messages", []) if isinstance(m, ToolMessage)]
    assert len(returned) == 1 and returned[0].tool_call_id == "bad"
    assert "invalid_arguments" in str(returned[0].content)
    assert_pairs(raw["messages"])


@pytest.mark.asyncio
async def test_strategy_propagates_cancelled_agent_without_evaluation():
    from deeptrace.strategies.workflow.graph import build_workflow_research_graph

    roles = []

    class CancelModel:
        async def invoke(self, *, role, messages, tools=None):
            roles.append(role)
            if role == "planner":
                return '{"queries": ["branch"]}'
            raise asyncio.CancelledError()

    fixture = build_gateway_fixture(model_gateway=CancelModel())
    graph = build_workflow_research_graph(build_research_agent_graph())
    # LangGraph distinguishes a provider-raised cancellation from task.cancel().
    from langgraph.errors import NodeCancelledError

    with pytest.raises(NodeCancelledError):
        await graph.ainvoke(
            {
                "run_id": "run-1",
                "thread_id": "thread-1",
                "question": "question",
                "current_date": "2026-09-18",
                "timezone": "UTC",
            },
            context=fixture.context,
        )
    assert roles == ["planner", "researcher"]


@pytest.mark.asyncio
@pytest.mark.parametrize("code,reason", [("budget_exhausted", "budget_exhausted"), ("tool_internal_error", "tool_error")])
async def test_terminal_tool_error_closes_pending_calls(code, reason):
    from deeptrace.domain import ToolResult
    from deeptrace.domain.errors import classify_error_code
    model = Model(AIMessage(content="", tool_calls=[
        call("search_web", {"query": "a"}, "a"),
        call("search_web", {"query": "b"}, "b"),
    ]))
    fixture = build_gateway_fixture(model_gateway=model)
    calls = []
    class FailedGateway:
        async def execute(self, **kwargs):
            request = kwargs["request"]
            calls.append(request)
            return ToolResult(request_id=request.request_id, run_id=request.run_id, thread_id=request.thread_id,
                              call_id=request.call_id, tool=request.tool, ok=False,
                              error_code=code, error_category=classify_error_code(code))
    raw = await build_research_agent_graph(max_tool_concurrency=1).ainvoke(
        {"topic_input": task()}, context=replace(fixture.context, tool_gateway=FailedGateway()))
    assert_pairs(raw["messages"])
    assert raw["outcome"].agent_outcome.stop_reason == reason
    assert len(calls) == 1 and len(model.calls) == 1


@pytest.mark.asyncio
async def test_checkpoint_serializes_plan_and_final_outcome():
    saver = InMemorySaver(serde=create_harness_checkpoint_serializer())
    fixture = build_gateway_fixture(model_gateway=Model(AIMessage(content="", tool_calls=[
        call("write_todos", {"todos": [{"content": "collect evidence", "status": "pending"}]}, "plan")
    ])))
    config = {"configurable": {"thread_id": "plan-resume"}}
    graph = build_research_agent_graph(max_iterations=2, checkpointer=saver)
    await graph.ainvoke({"topic_input": task()}, config=config, context=fixture.context,
                        interrupt_after=["execute_tools"])
    raw = await graph.ainvoke(None, config=config, context=replace(fixture.context, model_gateway=Model(AIMessage(content="done"))))
    checkpoint = await graph.aget_state(config)
    assert checkpoint.values["outcome"] == raw["outcome"]
    assert raw["outcome"].agent_outcome.unfinished_todos == ["collect evidence"]
    assert_pairs(checkpoint.values["messages"])


@pytest.mark.asyncio
async def test_invalid_fetch_arguments_still_finalize_cleanly():
    fixture = build_gateway_fixture(model_gateway=Model(AIMessage(content="", tool_calls=[
        call("fetch_page", {}, "bad-fetch")])))
    raw = await build_research_agent_graph(max_iterations=1).ainvoke({"topic_input": task()}, context=fixture.context)
    assert_pairs(raw["messages"])
    assert raw["outcome"].agent_outcome.stop_reason == "iteration_limit"
    assert raw["outcome"].errors[0].code == "invalid_arguments"
