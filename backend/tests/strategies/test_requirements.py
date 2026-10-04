"""Initial task decomposition is sealed once and survives checkpointing."""

import importlib
import importlib.util
import json

import pytest
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode, ResearchRequirement
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.multi_agent.nodes import build_supervisor_plan_node
from deeptrace.strategies.plan_execute.models import TaskPlan
from deeptrace.strategies.plan_execute.nodes import build_plan_node
from deeptrace.strategies.workflow.models import QueryPlan
from deeptrace.strategies.workflow.nodes import build_plan_queries_node
from strategies.fixtures import ScriptedModelGateway, build_gateway_fixture


def _module():
    assert (
        importlib.util.find_spec("deeptrace.strategies.evidence_evaluation") is not None
    )
    return importlib.import_module("deeptrace.strategies.evidence_evaluation")


def _state():
    return {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": "Compare Checkpoints and Store",
        "current_date": "2026-10-02",
        "timezone": "Asia/Shanghai",
    }


def _planner(mode):
    if mode is ResearchMode.WORKFLOW:
        return build_plan_queries_node(3), "planner", "queries"
    if mode is ResearchMode.PLAN_EXECUTE:
        return build_plan_node(3), "planner", "plan_tasks"
    return build_supervisor_plan_node(3), "supervisor", "assignments"


def test_failed_decomposition_keeps_full_original_task_as_one_requirement():
    requirements, degraded = _module().seal_requirements("Long task " * 1000, None)
    assert degraded is True
    assert requirements == [
        ResearchRequirement(id="r1", description="完整回答原始问题及全部用户约束")
    ]


def test_model_requirement_ids_are_host_renumbered_without_mutating_proposal():
    proposed = [
        ResearchRequirement(id="r2", description="Checkpoints"),
        ResearchRequirement(id="r1", description="Store"),
    ]
    requirements, degraded = _module().seal_requirements("Compare both", proposed)
    assert degraded is False
    assert [r.id for r in requirements] == ["r1", "r2"]
    assert [r.description for r in requirements] == ["Checkpoints", "Store"]
    assert proposed[0].id == "r2"


@pytest.mark.parametrize("model", [TaskPlan, QueryPlan])
def test_planning_contract_requires_a_bounded_requirement_list(model):
    from pydantic import ValidationError

    assert "requirements" in model.model_fields
    with pytest.raises(ValidationError):
        model(queries=["query"])
    with pytest.raises(ValidationError):
        model(queries=["query"], requirements=[])
    with pytest.raises(ValidationError):
        model(queries=["query"], requirements=[{"id": "r1", "description": "x"}] * 7)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("valid_requirements", [True, False])
async def test_initial_planning_seals_requirements_in_the_existing_model_call(
    mode, valid_requirements
):
    node, role, channel = _planner(mode)
    key = "assignments" if mode is ResearchMode.MULTI_AGENT else "queries"
    payload = {key: ["Checkpoints", "Store"]}
    if valid_requirements:
        payload["requirements"] = [
            {"id": "r2", "description": "Checkpoints"},
            {"id": "r1", "description": "Store"},
        ]
        payload["query_targets"] = {"Checkpoints": ["r2"], "Store": ["r1"]}
    model = ScriptedModelGateway({role: json.dumps(payload)})
    fixture = build_gateway_fixture(model_gateway=model)
    result = await node(_state(), Runtime(context=fixture.context))
    assert result.get("evidence_contract_version") == 3
    assert result.get("decomposition_degraded") is (not valid_requirements)
    assert [r.id for r in result["requirements"]] == (
        ["r1", "r2"] if valid_requirements else ["r1"]
    )
    assert result[channel] == (
        ["Checkpoints", "Store"] if valid_requirements else [_state()["question"]]
    )
    assert len(model.calls) == 1
    assert "requirements" in model.calls[0][1]
    serializer = create_harness_checkpoint_serializer()
    assert serializer.loads_typed(serializer.dumps_typed(result)) == result


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_invalid_requirement_schema_falls_back_without_losing_original_task(mode):
    node, role, channel = _planner(mode)
    key = "assignments" if mode is ResearchMode.MULTI_AGENT else "queries"
    payload = {
        key: ["a narrowed query"],
        "requirements": [{"id": "r1", "description": "x" * 501}],
    }
    model = ScriptedModelGateway({role: json.dumps(payload)})
    fixture = build_gateway_fixture(model_gateway=model)
    result = await node(_state(), Runtime(context=fixture.context))
    assert result.get("decomposition_degraded") is True
    assert result[channel] == [_state()["question"]]


def test_old_mid_research_snapshot_is_rejected_after_successful_decoding():
    serializer = create_harness_checkpoint_serializer()
    old = serializer.loads_typed(
        serializer.dumps_typed({**_state(), "evidence_ids": ["old"]})
    )
    with pytest.raises(ValueError, match="incompatible_evidence_contract"):
        _module().require_evidence_contract(old)


@pytest.mark.parametrize(
    "version,requirements",
    [
        (1, [ResearchRequirement(id="r1", description="task")]),
        (2, []),
        (2, [{"id": "r1", "description": "task"}] * 2),
    ],
)
def test_missing_or_invalid_sealed_requirements_cannot_resume(version, requirements):
    with pytest.raises(ValueError, match="incompatible_evidence_contract"):
        _module().require_evidence_contract(
            {"evidence_contract_version": version, "requirements": requirements}
        )


@pytest.mark.parametrize(
    "version,requirements",
    [
        (2.0, [{"id": "r1", "description": "task"}]),
        (2, [{"id": "r1", "description": "   "}]),
        (2, [{"id": "r2", "description": "task"}]),
    ],
)
def test_resume_requires_exact_host_seal_shape(version, requirements):
    with pytest.raises(ValueError, match="incompatible_evidence_contract"):
        _module().require_evidence_contract(
            {"evidence_contract_version": version, "requirements": requirements}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_long_task_fallback_bounds_only_discovery_query_not_completion_task(mode):
    from deeptrace.domain import ResearchTopicInput

    state = _state()
    state["question"] = "Explain Store " * 200
    node, role, channel = _planner(mode)
    model = ScriptedModelGateway({role: "invalid JSON"})
    fixture = build_gateway_fixture(model_gateway=model)
    result = await node(state, Runtime(context=fixture.context))
    query = result[channel][0]
    assert len(query) <= 1000
    assert state["question"] in model.calls[0][1]
    assert result["requirements"][0].description == "完整回答原始问题及全部用户约束"
    topic = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        mode=mode,
        query=query,
        original_task=state["question"],
        caller_id="test",
    )
    assert topic.original_task == state["question"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_actual_intermediate_nodes_reject_old_snapshots_before_models_or_tools(
    mode,
):
    from deeptrace.strategies.multi_agent.nodes import build_researcher_node
    from deeptrace.strategies.plan_execute.nodes import build_execute_task_node
    from deeptrace.strategies.workflow.nodes import build_research_topic_node

    class NoNewResearch:
        async def ainvoke(self, *args, **kwargs):
            raise AssertionError("old snapshot must not dispatch new research")

    nodes = {
        ResearchMode.PLAN_EXECUTE: build_execute_task_node,
        ResearchMode.WORKFLOW: build_research_topic_node,
        ResearchMode.MULTI_AGENT: build_researcher_node,
    }
    snapshot = {
        **_state(),
        "current_task": "Store",
        "query": "Store",
        "researcher_index": 0,
    }
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(snapshot))
    model = ScriptedModelGateway({})
    fixture = build_gateway_fixture(model_gateway=model)
    with pytest.raises(ValueError, match="incompatible_evidence_contract"):
        await nodes[mode](NoNewResearch())(
            restored, Runtime(context=fixture.context), {}
        )
    assert model.calls == fixture.gateway.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ResearchMode.PLAN_EXECUTE, ResearchMode.MULTI_AGENT])
async def test_supplement_planner_cannot_replace_sealed_requirements(mode):
    from deeptrace.strategies.multi_agent.nodes import build_follow_up_node
    from deeptrace.strategies.plan_execute.nodes import build_replan_node

    state = {
        **_state(),
        "evidence_contract_version": 3,
        "requirements": [
            ResearchRequirement(id="r1", description="whole original task")
        ],
    }
    role = "replanner" if mode is ResearchMode.PLAN_EXECUTE else "follow_up"
    key = "queries" if mode is ResearchMode.PLAN_EXECUTE else "assignments"
    model = ScriptedModelGateway(
        {
            role: json.dumps(
                {
                    key: ["Store"],
                    "requirements": [
                        {"id": "r1", "description": "a narrower easier task"}
                    ],
                }
            )
        }
    )
    fixture = build_gateway_fixture(model_gateway=model)
    factory = (
        build_replan_node if mode is ResearchMode.PLAN_EXECUTE else build_follow_up_node
    )
    updates = await factory(2)(state, Runtime(context=fixture.context))
    assert "requirements" not in updates
    assert state["requirements"][0].description == "whole original task"
