"""Known covered targets are pruned; unknown targets never acquire authority."""

import copy
import json

import pytest
from langgraph.runtime import Runtime

from deeptrace.domain import CoverageAssessment, ResearchMode, ResearchRequirement
from deeptrace.strategies.evidence_evaluation import parse_gap_tasks
from deeptrace.strategies.multi_agent.nodes import build_follow_up_node
from deeptrace.strategies.plan_execute.nodes import build_replan_node
from strategies.fixtures import ScriptedModelGateway, build_gateway_fixture


@pytest.mark.parametrize(
    ("targets", "expected"),
    [
        (["r3", "r2", "r1"], ["r2", "r1"]),
        (["r1", "r3"], ["r1"]),
        (["r3"], []),
        (["r1", "r9"], []),
        (["r1", "r1"], []),
        ([], []),
    ],
)
def test_targets_are_validated_against_sealed_ids_before_gap_intersection(
    targets, expected
):
    payload = {"tasks": [{"query": "new detail", "target_requirement_ids": targets}]}
    original = copy.deepcopy(payload)

    tasks = parse_gap_tasks(
        payload,
        gap_ids={"r1", "r2"},
        requirement_ids={"r1", "r2", "r3"},
        dispatched=[],
        limit=2,
    )

    assert [t.target_requirement_ids for t in tasks] == ([expected] if expected else [])
    assert payload == original


def test_rejected_targets_do_not_consume_query_identity_or_batch_capacity():
    payload = {
        "tasks": [
            {"query": "detail", "target_requirement_ids": ["r1", "r9"]},
            {"query": "detail", "target_requirement_ids": ["r3"]},
            {"query": "detail", "target_requirement_ids": ["r3", "r1"]},
            {"query": " DETAIL ", "target_requirement_ids": ["r1"]},
            {"query": "other detail", "target_requirement_ids": ["r1"]},
            {"query": "excess detail", "target_requirement_ids": ["r1"]},
        ]
    }

    tasks = parse_gap_tasks(
        payload,
        gap_ids={"r1"},
        requirement_ids={"r1", "r3"},
        dispatched=[],
        limit=6,
    )

    assert [(t.query, t.target_requirement_ids) for t in tasks] == [
        ("detail", ["r1"]),
        ("other detail", ["r1"]),
    ]


def test_host_gap_ids_must_be_subset_of_the_sealed_contract():
    with pytest.raises(ValueError, match="invalid_gap_ids"):
        parse_gap_tasks(
            {"tasks": []},
            gap_ids={"r9"},
            requirement_ids={"r1"},
            dispatched=[],
            limit=2,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ResearchMode.PLAN_EXECUTE, ResearchMode.MULTI_AGENT])
async def test_actual_supplement_nodes_dispatch_mixed_targets_without_resealing(mode):
    requirements = [
        ResearchRequirement(id="r1", description="thread_id reason"),
        ResearchRequirement(id="r2", description="snapshot boundary"),
    ]
    state = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": "Explain checkpoints",
        "current_date": "2026-10-02",
        "timezone": "Asia/Shanghai",
        "evidence_contract_version": 3,
        "requirements": requirements,
        "coverage": CoverageAssessment(
            items=[
                {
                    "requirement_id": "r1",
                    "status": "missing",
                    "reason": "need thread_id",
                },
                {
                    "requirement_id": "r2",
                    "status": "covered",
                    "reason": "boundary known",
                },
            ]
        ),
    }
    role = "replanner" if mode is ResearchMode.PLAN_EXECUTE else "follow_up"
    model = ScriptedModelGateway(
        {
            role: json.dumps(
                {
                    "tasks": [
                        {
                            "query": "thread_id detail",
                            "target_requirement_ids": ["r1", "r2"],
                        }
                    ]
                }
            )
        }
    )
    fixture = build_gateway_fixture(model_gateway=model)
    factory = (
        build_replan_node if mode is ResearchMode.PLAN_EXECUTE else build_follow_up_node
    )

    updates = await factory(2)(state, Runtime(context=fixture.context))

    key = "plan_tasks" if mode is ResearchMode.PLAN_EXECUTE else "assignments"
    assert updates[key] == ["thread_id detail"]
    assert updates["supplement_targets"] == {"thread_id detail": ["r1"]}
    assert "requirements" not in updates
    assert state["requirements"] == requirements
