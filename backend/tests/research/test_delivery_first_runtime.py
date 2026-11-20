"""Delivery-first collection stops without a fact-coverage research loop."""

import asyncio
import json

import pytest
from deeptrace.domain import ResearchMode
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.model_budget import BudgetStateUnavailable
from deeptrace.research.runtime import build_controller_research_graph
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import NodeCancelledError
from strategies.fixtures import build_gateway_fixture
from strategies.workflow.test_graph import _research_input


class Planner:
    def __init__(self):
        self.roles = []

    async def invoke(self, *, role, messages, tools=None):
        self.roles.append(role)
        if role not in {"planner", "supervisor"}:
            raise AssertionError("collection must not call a coverage evaluator")
        return AIMessage(
            content=json.dumps(
                {
                    "requirements": [
                        {"id": "r1", "description": "first rule"},
                        {"id": "r2", "description": "an unavailable detail"},
                    ],
                    "tasks": [
                        {
                            "id": "t1",
                            "query": "topic-one",
                            "requirement_ids": ["r1"],
                            "read_terms": ["first rule"],
                        },
                        {
                            "id": "t2",
                            "query": "topic-two",
                            "requirement_ids": ["r2"],
                            "read_terms": ["second rule"],
                        },
                    ],
                }
            )
        )


def fixture_for(model):
    return build_gateway_fixture(
        model_gateway=model,
        search_results={
            "topic-one": [{"url": "https://example.com/one", "title": "one"}],
            "topic-two": [{"url": "https://example.com/two", "title": "two"}],
        },
        pages={
            "https://example.com/one": "The first rule is documented.",
            "https://example.com/two": "The second rule lacks the requested detail.",
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_actual_reads_reach_delivery_without_evaluator_or_replanner(mode):
    model = Planner()
    fixture = fixture_for(model)
    graph = build_controller_research_graph(build_batch_research_graph(), mode=mode)
    result = await graph.ainvoke(
        _research_input("Compare the rules and disclose unknown detail"),
        context=fixture.context,
    )
    outcome = result["outcome"]
    assert outcome.delivery_first
    assert len(outcome.evidence_ids) == 2
    assert outcome.read_anchors
    assert outcome.coverage is None
    assert outcome.termination_reason == "completed"
    assert model.roles == [
        "supervisor" if mode is ResearchMode.MULTI_AGENT else "planner"
    ]
    assert not any("evaluation" in t for t, _ in fixture.events.events)


@pytest.mark.asyncio
async def test_failed_parallel_sibling_preserves_successful_material_and_limitation():
    fixture = fixture_for(Planner())
    inner = build_batch_research_graph()

    class Branches:
        async def ainvoke(self, data, **kwargs):
            if data["topic_input"].query == "topic-two":
                raise RuntimeError("source unavailable")
            return await inner.ainvoke(data, **kwargs)

    result = await build_controller_research_graph(
        Branches(), mode=ResearchMode.MULTI_AGENT
    ).ainvoke(_research_input("Compare the rules"), context=fixture.context)
    assert result["outcome"].delivery_first
    assert len(result["outcome"].evidence_ids) == 1
    assert result["outcome"].read_anchors
    assert result["outcome"].unresolved_gaps


@pytest.mark.asyncio
async def test_plan_execute_receives_previous_material_while_independent_modes_do_not():
    for mode in ResearchMode:
        fixture = fixture_for(Planner())
        inner = build_batch_research_graph()
        seen = []

        class Branches:
            async def ainvoke(self, data, _seen=seen, _inner=inner, **kwargs):
                _seen.append(data["topic_input"])
                return await _inner.ainvoke(data, **kwargs)

        await build_controller_research_graph(Branches(), mode=mode).ainvoke(
            _research_input("Compare the rules"), context=fixture.context
        )
        second = next(x for x in seen if x.query == "topic-two")
        assert bool(second.authorized_evidence_ids) == (
            mode is ResearchMode.PLAN_EXECUTE
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        PermissionError,
        asyncio.CancelledError,
        BudgetStateUnavailable,
        NodeCancelledError,
    ],
)
async def test_authorization_cancellation_and_budget_store_failure_propagate(error):
    fixture = fixture_for(Planner())

    class Branch:
        async def ainvoke(self, *args, **kwargs):
            raise error("child") if error is NodeCancelledError else error()

    with pytest.raises((error, NodeCancelledError)):
        await build_controller_research_graph(Branch()).ainvoke(
            _research_input("Compare"), context=fixture.context
        )


@pytest.mark.asyncio
async def test_budget_exhaustion_stops_collection_but_keeps_material_for_writer():
    model = Planner()
    model.research_exhausted = False
    fixture = fixture_for(model)
    inner = build_batch_research_graph()
    calls = []

    class Branch:
        async def ainvoke(self, data, **kwargs):
            calls.append(data["topic_input"].query)
            outcome = await inner.ainvoke(data, **kwargs)
            model.research_exhausted = True
            return outcome

    result = await build_controller_research_graph(Branch()).ainvoke(
        _research_input("Compare"), context=fixture.context
    )
    assert calls == ["topic-one"]
    assert result["outcome"].read_anchors
    assert any("topic-two" in g for g in result["outcome"].unresolved_gaps)


@pytest.mark.asyncio
async def test_new_run_on_same_checkpoint_clears_previous_collection():
    fixture = fixture_for(Planner())
    topic = build_batch_research_graph()
    graph = build_controller_research_graph(topic, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "two-runs"}}
    await graph.ainvoke(
        _research_input("First"), config=config, context=fixture.context
    )
    fixture.context.model_gateway.research_exhausted = True
    second = await graph.ainvoke(
        {**_research_input("Second"), "run_id": "run-second"},
        config=config,
        context=fixture.context,
    )
    assert second["outcome"].evidence_ids == []
    assert second["outcome"].read_anchors == []


@pytest.mark.asyncio
async def test_sqlite_resume_reuses_finished_sibling_after_cancel(tmp_path):
    from deeptrace.persistence.checkpoint import SqlAlchemyCheckpointSaver
    from deeptrace.persistence.database import create_session_factory
    from deeptrace.persistence.orm import Base

    engine, sessions = create_session_factory(
        f"sqlite+aiosqlite:///{tmp_path}/resume.db"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fixture = fixture_for(Planner())
    inner = build_batch_research_graph()
    calls = []
    first = asyncio.Event()
    saver = SqlAlchemyCheckpointSaver(sessions)

    class Branch:
        async def ainvoke(self, data, **kwargs):
            query = data["topic_input"].query
            calls.append(query)
            if query == "topic-two" and calls.count(query) == 1:
                await first.wait()
                await asyncio.sleep(0.05)
                raise asyncio.CancelledError()
            outcome = await inner.ainvoke(data, **kwargs)
            first.set()
            return outcome

    config = {"configurable": {"thread_id": "resume-new-runtime"}}
    try:
        graph = build_controller_research_graph(
            Branch(), mode=ResearchMode.MULTI_AGENT, checkpointer=saver
        )
        with pytest.raises((asyncio.CancelledError, NodeCancelledError)):
            await graph.ainvoke(
                _research_input("Compare"), config=config, context=fixture.context
            )
        restarted = build_controller_research_graph(
            Branch(), mode=ResearchMode.MULTI_AGENT, checkpointer=saver
        )
        result = await restarted.ainvoke(None, config=config, context=fixture.context)
        assert calls.count("topic-one") == 1
        assert calls.count("topic-two") == 2
        assert len(result["outcome"].evidence_ids) == 2
        assert fixture.context.model_gateway.roles == ["supervisor"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_bad_optional_plan_metadata_keeps_valid_queries_and_read_terms():
    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(
                content=json.dumps(
                    {
                        "requirements": [{"id": "r1", "description": "rule"}],
                        "tasks": [
                            {
                                "id": "t1",
                                "query": "topic-one",
                                "requirement_ids": ["bad-id"],
                                "read_terms": ["first rule"],
                            }
                        ],
                    }
                )
            )

    fixture = fixture_for(Model())
    result = await build_controller_research_graph(
        build_batch_research_graph()
    ).ainvoke(_research_input("Original question"), context=fixture.context)
    assert result["queries"] == ["topic-one"]
    assert result["outcome"].read_anchors


@pytest.mark.asyncio
async def test_initial_plan_dispatches_a_query_for_an_unassigned_fact():
    from research.test_runtime import CaptureTopic

    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({
                "requirements": [
                    {"id": "r1", "description": "Global annual installations"},
                    {"id": "r2", "description": "China annual installations"},
                    {"id": "r3", "description": "Format as a table", "kind": "output_criterion"},
                ],
                "tasks": [{"query": "global installations", "requirement_ids": ["r1"]}],
            }))

    topic = CaptureTopic()
    await build_controller_research_graph(topic, max_rounds=1).ainvoke(
        _research_input("Compare global and China installations"), context=fixture_for(Model()).context,
    )
    assert [(task.query, task.target_requirement_ids) for task in topic.requests] == [
        ("global installations", ["r1"]), ("China annual installations", ["r2"]),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("missing", [True, False])
async def test_first_round_review_only_collects_new_queries_for_required_gaps(mode, missing):
    class Model(Planner):
        async def invoke(self, *, role, messages, tools=None):
            if role != "coverage_reviewer":
                return await super().invoke(role=role, messages=messages, tools=tools)
            assert "The first rule is documented." in messages[-1].content
            self.roles.append(role)
            return AIMessage(content=json.dumps({
                "covered_requirement_ids": ["r1"] if missing else ["r1", "r2"],
                "tasks": [
                    {"query": " TOPIC-ONE ", "target_requirement_ids": ["r2"]},
                    {"query": "irrelevant", "target_requirement_ids": ["r1"]},
                    {"query": "second rule official addendum", "target_requirement_ids": ["r2"]},
                ],
            }))

    model = Model()
    fixture = build_gateway_fixture(
        model_gateway=model,
        search_results={
            "topic-one": [{"url": "https://example.com/one", "title": "one"}],
            "topic-two": [{"url": "https://example.com/two", "title": "two"}],
            "second rule official addendum": [{"url": "https://example.com/addendum", "title": "addendum"}],
        },
        pages={
            "https://example.com/one": "The first rule is documented.",
            "https://example.com/two": "The second rule lacks the requested detail.",
            "https://example.com/addendum": "The second rule requires a separate permit.",
        },
    )
    inner = build_batch_research_graph()
    tasks = []

    class Branch:
        async def ainvoke(self, data, **kwargs):
            tasks.append(data["topic_input"])
            return await inner.ainvoke(data, **kwargs)

    state = await build_controller_research_graph(Branch(), mode=mode, max_rounds=2).ainvoke(
        _research_input("What do both rules require?"), context=fixture.context,
    )
    assert sorted(task.query for task in tasks) == sorted(
        ["topic-one", "topic-two"] + (["second rule official addendum"] if missing else [])
    )
    assert model.roles.count("coverage_reviewer") == 1
    assert len(state["outcome"].read_anchors) == (3 if missing else 2)
    if missing:
        targeted = next(task for task in tasks if task.query == "second rule official addendum")
        assert targeted.target_requirement_ids == ["r2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,width",
    [
        (ResearchMode.WORKFLOW, 1),
        (ResearchMode.PLAN_EXECUTE, 1),
        (ResearchMode.MULTI_AGENT, 2),
    ],
)
async def test_modes_keep_real_serial_or_parallel_scheduling(mode, width):
    fixture = fixture_for(Planner())
    active = 0
    peak = 0

    class Branch:
        async def ainvoke(self, data, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return {
                "outcome": {"query": data["topic_input"].query, "executed_steps": 1}
            }

    await build_controller_research_graph(Branch(), mode=mode, max_parallel=2).ainvoke(
        _research_input("Compare"), context=fixture.context
    )
    assert peak == width
