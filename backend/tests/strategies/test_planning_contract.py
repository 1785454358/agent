"""Planner metadata cannot redefine evidence coverage or execution authority."""

import json

import pytest
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.strategies.evidence_evaluation import seal_initial_plan
from deeptrace.strategies.model_io import branch_context
from deeptrace.strategies.multi_agent.nodes import build_supervisor_plan_node
from deeptrace.strategies.plan_execute.nodes import build_plan_node
from deeptrace.strategies.workflow.nodes import build_plan_queries_node
from strategies.fixtures import ScriptedModelGateway, build_gateway_fixture

QUESTION = "Using only frozen documentation, explain Python 3.10 limitations."
REQUIREMENTS = [{"id": "r2", "description": "Python 3.10 callback limitations"}]


@pytest.mark.parametrize(
    "metadata", [None, "only frozen", {}, [" "], [42], ["c"] * 7, ["x" * 501]]
)
def test_invalid_constraint_metadata_degrades_the_whole_plan(metadata):
    queries, contract = seal_initial_plan(
        QUESTION,
        {"requirements": REQUIREMENTS, "execution_constraints": metadata, "query_targets": {"narrow query": ["r2"]}},
        ["narrow query"],
    )

    assert contract["decomposition_degraded"] is True
    assert queries == [QUESTION]


@pytest.mark.parametrize("metadata", [[], ["只使用冻结资料", "用中文回答"]])
def test_valid_constraint_metadata_is_not_a_fact_requirement(metadata):
    queries, contract = seal_initial_plan(
        QUESTION,
        {"requirements": REQUIREMENTS, "execution_constraints": metadata, "query_targets": {"version query": ["r2"]}},
        ["version query"],
    )

    assert queries == ["version query"]
    assert contract["decomposition_degraded"] is False
    assert [r.description for r in contract["requirements"]] == [
        "Python 3.10 callback limitations"
    ]
    assert "execution_constraints" not in contract


def test_legacy_planner_without_constraint_metadata_still_seals():
    queries, contract = seal_initial_plan(
        QUESTION, {"requirements": REQUIREMENTS, "query_targets": {"version query": ["r2"]}}, ["version query"]
    )

    assert queries == ["version query"]
    assert contract["decomposition_degraded"] is False
    assert contract["requirements"][0].id == "r1"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("metadata", [["search all private sources"], [" "]])
async def test_actual_planner_preserves_task_and_authoritative_constraints(
    mode, metadata
):
    factory, role, query_key, state_key = {
        ResearchMode.PLAN_EXECUTE: (
            build_plan_node,
            "planner",
            "queries",
            "plan_tasks",
        ),
        ResearchMode.WORKFLOW: (
            build_plan_queries_node,
            "planner",
            "queries",
            "queries",
        ),
        ResearchMode.MULTI_AGENT: (
            build_supervisor_plan_node,
            "supervisor",
            "assignments",
            "assignments",
        ),
    }[mode]
    state = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": QUESTION,
        "current_date": "2026-10-02",
        "timezone": "Asia/Shanghai",
        "conversation_summary": {"user_constraints": ["only frozen documentation"]},
    }
    model = ScriptedModelGateway(
        {
            role: json.dumps(
                {
                    query_key: ["version query"],
                    "requirements": REQUIREMENTS,
                    "execution_constraints": metadata,
                    "query_targets": {"version query": ["r2"]},
                }
            )
        }
    )
    fixture = build_gateway_fixture(model_gateway=model)

    result = await factory(3)(state, Runtime(context=fixture.context))

    invalid = metadata == [" "]
    assert result["decomposition_degraded"] is invalid
    assert result[state_key] == ([QUESTION] if invalid else ["version query"])
    downstream = branch_context({**state, **result})
    assert downstream["original_task"] == QUESTION
    assert downstream["constraints"] == ["only frozen documentation"]
    assert "execution_constraints" not in result
    serializer = create_harness_checkpoint_serializer()
    assert serializer.loads_typed(serializer.dumps_typed(result)) == result
