"""Plan 7 exit gate: forced crashes resume from durable checkpoints without
repeating completed side effects."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from langgraph.checkpoint.base import BaseCheckpointSaver

from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.persistence.checkpoint import SqlAlchemyCheckpointSaver
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.execution_ledger import SqlAlchemyToolExecutionStore
from deeptrace.persistence.orm import Base
from langgraph.errors import NodeCancelledError
from deeptrace.responses import build_answer_graph
from deeptrace.strategies import (
    build_research_topic_graph,
    build_workflow_research_graph,
)

from strategies.fixtures import build_gateway_fixture


class CrashError(RuntimeError):
    """Simulates a worker process crash at an arbitrary await point."""


class CrashOnceModelGateway:
    """Fails the requested role on its first call, then behaves normally."""

    def __init__(self, responses: dict[str, Any], crash_role: str) -> None:
        self._responses = responses
        self._crash_role = crash_role
        self.calls: list[str] = []

    async def invoke(self, *, role: str, messages: list[Any]) -> Any:
        self.calls.append(role)
        if role == self._crash_role and self.calls.count(role) == 1:
            raise CrashError("worker crashed")
        return self._responses[role](str(messages[-1].content))


class CrashProxy:
    """Simulates a worker crash at a graph boundary via CancelledError.

    Ordinary exceptions are deliberately swallowed by strategy nodes (task-local
    failure semantics); a real worker crash surfaces as task cancellation, which
    is exactly what recovery must survive.
    """

    def __init__(self, inner, *, after_completion: bool) -> None:
        self._inner = inner
        self._after_completion = after_completion
        self.calls = 0

    async def ainvoke(self, input_data, config=None, **kwargs):
        self.calls += 1
        if self._after_completion and self.calls == 1:
            result = await self._inner.ainvoke(input_data, config=config, **kwargs)
            raise asyncio.CancelledError("worker process crashed")
        if self._after_completion:
            return await self._inner.ainvoke(input_data, config=config, **kwargs)
        if self.calls == 1:
            raise asyncio.CancelledError("worker process crashed")
        return await self._inner.ainvoke(input_data, config=config, **kwargs)


def _evaluation(prompt: str) -> str:
    ids = sorted(set(re.findall(r"evidence-[0-9a-f]+", prompt)))
    return json.dumps(
        {
            "findings": [
                {
                    "id": "finding-1",
                    "claim": "已获得可用资料",
                    "evidence_ids": ids[:1],
                    "confidence": 0.9,
                }
            ],
            "unresolved_gaps": [],
            "sufficient": True,
        }
    )


def _registries(topic_proxy=None, response_proxy=None):
    topic_graph = build_research_topic_graph()
    if topic_proxy is not None:
        topic_graph = topic_proxy
    strategies = StrategyRegistry()
    strategies.register(
        StrategyRegistration(
            ResearchMode.WORKFLOW,
            build_workflow_research_graph(topic_graph),
        )
    )
    responses = ResponseGraphRegistry()
    answer_graph = build_answer_graph()
    if response_proxy is not None:
        answer_graph = response_proxy
    responses.register(ResponseRegistration(ResponseMode.ANSWER, answer_graph))
    return strategies, responses


async def _setup(tmp_path):
    engine, sessions = create_session_factory(
        f"sqlite+aiosqlite:///{tmp_path}/recovery.db"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    saver = SqlAlchemyCheckpointSaver(sessions)
    ledger = SqlAlchemyToolExecutionStore(sessions, poll_interval_seconds=0.01)
    return saver, ledger


@pytest.mark.asyncio
async def test_crash_during_planning_resumes_without_repeating_tools(tmp_path) -> None:
    saver, ledger = await _setup(tmp_path)
    model = CrashOnceModelGateway(
        responses={
            "planner": lambda prompt: json.dumps({"queries": ["研究问题"]}),
            "evaluator": _evaluation,
            "responder": lambda prompt: json.dumps({"content": "结论 [1]。"}),
        },
        crash_role="planner",
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究问题": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "recovery-body-a"},
        model_gateway=model,
        execution_store=ledger,
    )
    crashing_topic = CrashProxy(build_research_topic_graph(), after_completion=False)
    strategies, responses = _registries(topic_proxy=crashing_topic)
    graph = build_agent_runtime_graph(
        strategies, responses, checkpointer=saver
    )
    initial = {
        "conversation": _new_conversation("thread-1"),
        "turn": _new_turn("run-1", "研究问题"),
    }
    config = {"configurable": {"thread_id": "thread-1"}}

    with pytest.raises(NodeCancelledError):
        await graph.ainvoke(initial, config=config, context=fixture.context)

    result = await graph.ainvoke(None, config=config, context=fixture.context)

    turn = result["turn"]
    assert turn["status"] == "completed"
    assert turn["response_outcome"].cited_evidence_ids
    assert [call["request"].tool.value for call in fixture.gateway.calls] == [
        "search_web",
        "fetch_page",
    ]
    assert fixture.search.calls == ["研究问题"]
    assert fixture.fetcher.calls == ["https://example.com/a"]


def _new_conversation(thread_id: str):
    from deeptrace.domain import ConversationSummary, ResearchMode
    from deeptrace.harness.state import new_conversation

    return new_conversation(thread_id, ResearchMode.WORKFLOW)


def _new_turn(run_id: str, question: str):
    from deeptrace.domain import ResearchMode
    from deeptrace.harness.state import new_turn

    return new_turn(run_id, question, ResearchMode.WORKFLOW)


@pytest.mark.asyncio
async def test_crash_after_tool_execution_replays_ledger_on_resume(tmp_path) -> None:
    saver, ledger = await _setup(tmp_path)
    model = CrashOnceModelGateway(
        responses={
            "planner": lambda prompt: json.dumps({"queries": ["研究问题"]}),
            "evaluator": _evaluation,
            "responder": lambda prompt: json.dumps({"content": "结论 [1]。"}),
        },
        crash_role="__never__",
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究问题": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "recovery-body-b"},
        model_gateway=model,
        execution_store=ledger,
    )
    crashing_topic = CrashProxy(build_research_topic_graph(), after_completion=True)
    strategies, responses = _registries(topic_proxy=crashing_topic)
    graph = build_agent_runtime_graph(
        strategies, responses, checkpointer=saver
    )
    initial = {
        "conversation": _new_conversation("thread-1"),
        "turn": _new_turn("run-1", "研究问题"),
    }
    config = {"configurable": {"thread_id": "thread-1"}}

    with pytest.raises(NodeCancelledError):
        await graph.ainvoke(initial, config=config, context=fixture.context)

    result = await graph.ainvoke(None, config=config, context=fixture.context)

    turn = result["turn"]
    assert turn["status"] == "completed"
    # The topic subgraph ran twice, but its own checkpoint was already at the
    # final state: the resume reused the completed result and re-executed zero
    # nodes — no provider call, ledger entry, or evidence ingest happened twice.
    assert crashing_topic.calls == 2
    assert fixture.search.calls == ["研究问题"]
    assert fixture.fetcher.calls == ["https://example.com/a"]
    assert len(fixture.gateway.calls) == 2


@pytest.mark.asyncio
async def test_crash_after_memory_commit_does_not_duplicate_facts(tmp_path) -> None:
    from deeptrace.harness.memory.write import remember, MemoryWritePolicy
    from deeptrace.domain import MemoryRecord, MemoryType

    saver, ledger = await _setup(tmp_path)
    model = CrashOnceModelGateway(
        responses={
            "planner": lambda prompt: json.dumps({"queries": ["研究问题"]}),
            "evaluator": _evaluation,
            "responder": lambda prompt: json.dumps({"content": "结论 [1]。"}),
        },
        crash_role="responder",
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究问题": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "recovery-body-c"},
        model_gateway=model,
        execution_store=ledger,
    )
    strategies, responses = _registries()
    graph = build_agent_runtime_graph(
        strategies, responses, checkpointer=saver
    )
    initial = {
        "conversation": _new_conversation("thread-1"),
        "turn": _new_turn("run-1", "研究问题"),
    }
    config = {"configurable": {"thread_id": "thread-1"}}

    with pytest.raises(RuntimeError):
        await graph.ainvoke(initial, config=config, context=fixture.context)

    result = await graph.ainvoke(None, config=config, context=fixture.context)

    assert result["turn"]["status"] == "completed"
    # consolidation re-ran after resume but the versioned upsert is idempotent
    facts = await fixture.memory_store.list_namespace(
        ("workspace", "workspace-1", "facts")
    )
    assert len(facts) == 1
    assert fixture.fetcher.calls == ["https://example.com/a"]


@pytest.mark.asyncio
async def test_checkpointer_supports_explicit_checkpoint_id_and_filtered_list(
    tmp_path,
) -> None:
    saver, _ledger = await _setup(tmp_path)
    model = CrashOnceModelGateway(
        responses={
            "planner": lambda prompt: json.dumps({"queries": ["研究问题"]}),
            "evaluator": _evaluation,
            "responder": lambda prompt: json.dumps({"content": "结论 [1]。"}),
        },
        crash_role="__never__",
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究问题": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "body-a"},
        model_gateway=model,
    )
    strategies, responses = _registries()
    graph = build_agent_runtime_graph(strategies, responses, checkpointer=saver)
    config = {"configurable": {"thread_id": "thread-1"}}

    await graph.ainvoke(
        {
            "conversation": _new_conversation("thread-1"),
            "turn": _new_turn("run-1", "研究问题"),
        },
        config=config,
        context=fixture.context,
    )
    checkpoints = [
        item async for item in saver.alist(config, limit=100)
    ]
    assert len(checkpoints) >= 2

    # explicit checkpoint_id reads that historical state (time travel / fork)
    historical = checkpoints[2] if len(checkpoints) > 2 else checkpoints[0]
    pointed = await saver.aget_tuple(
        {
            "configurable": {
                "thread_id": "thread-1",
                "checkpoint_id": historical.config["configurable"]["checkpoint_id"],
            }
        }
    )
    assert pointed is not None
    assert (
        pointed.config["configurable"]["checkpoint_id"]
        == historical.config["configurable"]["checkpoint_id"]
    )

    # filtered + limited listing: filter selects nothing -> empty, not garbage
    listed = [
        item
        async for item in saver.alist(
            config, filter={"source": "no-such-value"}, limit=5
        )
    ]
    assert listed == []


@pytest.mark.asyncio
async def test_service_resumes_an_interrupted_run_for_the_same_identity(
    tmp_path,
) -> None:
    """Worker-chain crash: the same run request resumes instead of restarting."""
    from deeptrace.application.research import (
        ApplicationResearchRequest,
        ResearchApplicationService,
    )

    saver, ledger = await _setup(tmp_path)
    model = CrashOnceModelGateway(
        responses={
            "planner": lambda prompt: json.dumps({"queries": ["研究问题"]}),
            "evaluator": _evaluation,
            "responder": lambda prompt: json.dumps({"content": "结论 [1]。"}),
        },
        crash_role="__never__",
    )
    fixture = build_gateway_fixture(
        search_results={
            "研究问题": [
                {"url": "https://example.com/a", "title": "A", "snippet": "s"}
            ]
        },
        pages={"https://example.com/a": "service-resume-body"},
        model_gateway=model,
        execution_store=ledger,
    )
    crashing_topic = CrashProxy(
        build_research_topic_graph(), after_completion=False
    )
    strategies, responses = _registries(topic_proxy=crashing_topic)
    graph = build_agent_runtime_graph(strategies, responses, checkpointer=saver)
    service = ResearchApplicationService(graph)
    request = ApplicationResearchRequest(
        run_id="run-1",
        thread_id="thread-1",
        question="研究问题",
        mode=ResearchMode.WORKFLOW,
    )
    config = {"configurable": {"thread_id": "thread-1"}}

    with pytest.raises(NodeCancelledError):
        await service.invoke(request, config=config, context=fixture.context)

    # same run identity again: the service resumes the interrupted run
    outcome = await service.invoke(
        request, config=config, context=fixture.context
    )

    assert outcome.partial_reason is None
    assert outcome.cited_evidence_ids
    # the planner ran exactly once across both attempts (no restart from zero)
    assert model.calls.count("planner") == 1
    assert fixture.search.calls == ["研究问题"]
    assert fixture.fetcher.calls == ["https://example.com/a"]
