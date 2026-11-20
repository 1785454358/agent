"""Execution completion is distinct from supported research coverage."""

import pytest

from deeptrace.domain import (
    ResearchMode,
    ResearchOutcome,
    ResponseMode,
    ResponseOutcome,
)
from deeptrace.harness.graph import _finalize_turn
from deeptrace.harness.state import new_turn
from deeptrace.strategies.multi_agent.nodes import (
    build_route_after_evaluate as multi_route,
)
from deeptrace.strategies.plan_execute.nodes import build_route_after_evaluate


@pytest.mark.parametrize(
    "mode,expected",
    [
        (ResearchMode.WORKFLOW, "completed"),
        (ResearchMode.PLAN_EXECUTE, "partial"),
        (ResearchMode.MULTI_AGENT, "partial"),
    ],
)
def test_fixed_flow_finishes_without_erasing_evidence_gaps(mode, expected):
    research = ResearchOutcome(
        mode=mode,
        evidence_contract_version=3,
        executed_steps=5,
        requirements=[{"id": "r1", "description": "required detail"}],
        coverage={
            "items": [
                {"requirement_id": "r1", "status": "missing", "reason": "no source"}
            ]
        },
        unresolved_gaps=["r1:missing:no source"],
        termination_reason="insufficient_evidence",
    )
    turn = {
        **new_turn("run-1", "question", mode),
        "research_outcome": research,
        "response_outcome": ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="No supporting evidence was obtained.",
            partial_reason="no_evidence",
        ),
    }
    result = _finalize_turn({"turn": turn})["turn"]
    assert result["status"] == expected
    assert result["research_outcome"].unresolved_gaps == ["r1:missing:no source"]
    assert result["response_outcome"].partial_reason == "no_evidence"


@pytest.mark.parametrize(
    "route,key,next_node",
    [
        (build_route_after_evaluate, "decision", "replan"),
        (multi_route, "evaluation", "follow_up"),
    ],
)
def test_unavailable_evaluation_gets_bounded_supplement_instead_of_early_exit(
    route, key, next_node
):
    state = {
        "evidence_ids": ["e1"],
        key: None,
        "requirements": [{"id": "r1", "description": "detail"}],
        "coverage": {
            "items": [
                {
                    "requirement_id": "r1",
                    "status": "missing",
                    "reason": "evaluation unavailable",
                }
            ]
        },
    }
    assert route(2)(state) == next_node
    assert route(2)({**state, "replan_count": 2, "round_number": 2}) == "finalize"


@pytest.mark.parametrize("route", [build_route_after_evaluate, multi_route])
def test_model_budget_denial_does_not_attempt_supplement(route):
    state = {"evidence_ids": ["e1"], "diagnostic_gaps": ["evaluation_budget_exhausted"]}
    assert route(2)(state) == "finalize"
