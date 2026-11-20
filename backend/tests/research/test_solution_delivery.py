"""A selected solution determines acquisition; mappings alone are not searches."""

import copy
import json

import pytest
from langchain_core.messages import AIMessage

from deeptrace.research.runtime import build_controller_research_graph
from deeptrace.strategies.evidence_evaluation import seal_initial_plan
from research.test_runtime import CaptureTopic, request
from strategies.fixtures import build_gateway_fixture


def solution_payload():
    needs = [
        ("r1", "Selected attraction admission", "selected museum admission"),
        ("r2", "Accommodation reference", "central room dated occupancy price"),
        ("r3", "Food reference", "local meals dated per-person prices"),
        ("r4", "Transport for every selected leg", "selected route transport fares and coverage"),
    ]
    return {
        "queries": ["all tourist sights"],
        "requirements": [{"id": key, "description": description, "kind": "fact"}
                         for key, description, _ in needs],
        "query_targets": {"all tourist sights": [n[0] for n in needs]},
        "research_brief": {"objective": "A usable short trip", "scope": "Selected city route",
                           "assumptions": ["One person"], "answer_expectation": "Route and cost"},
        "task_briefs": {"all tourist sights": {
            "objective": "Selected visit", "boundary": "Necessary facts",
            "source_strategy": "Dated originals", "expected_output": "Prices and restrictions",
            "search_queries": ["all tourist sights"],
        }},
        "delivery_plan": {
            "approach": "One compact city route with central accommodation",
            "assumptions": ["One person, two nights, weekdays"],
            "outline": ["Visit the selected museum", "Stay near transport and eat locally"],
            "evidence_needs": [{"requirement_id": key, "query": query} for key, _, query in needs],
            "consistency_checks": ["Transport includes every selected route leg",
                                   "Costs use one-person occupancy and add up within the cap"],
        },
    }


def test_selected_solution_survives_sealing_without_becoming_evidence():
    data = solution_payload()
    original = copy.deepcopy(data)
    _, sealed = seal_initial_plan("Plan a short trip", data, data["queries"])
    assert sealed["delivery_plan"].approach == "One compact city route with central accommodation"
    assert len(sealed["requirements"]) == 4
    assert data == original


def test_solution_references_follow_host_requirement_renumbering():
    data = solution_payload()
    for row in data["requirements"]:
        row["id"] = {"r1": "r2", "r2": "r3", "r3": "r4", "r4": "r6"}[row["id"]]
    data["query_targets"] = {"all tourist sights": ["r2", "r3", "r4", "r6"]}
    for row, identity in zip(data["delivery_plan"]["evidence_needs"], ["r2", "r3", "r4", "r6"]):
        row["requirement_id"] = identity
    _, sealed = seal_initial_plan("Plan a short trip", data, data["queries"])
    assert [n.requirement_id for n in sealed["delivery_plan"].evidence_needs] == ["r1", "r2", "r3", "r4"]


@pytest.mark.parametrize("defect", ["unknown", "duplicate", "missing"])
def test_bad_solution_is_rejected_locally_without_destroying_legal_queries(defect):
    data = solution_payload()
    needs = data["delivery_plan"]["evidence_needs"]
    if defect == "unknown":
        needs[-1]["requirement_id"] = "r6"
    elif defect == "duplicate":
        needs[-1]["requirement_id"] = "r1"
    else:
        needs.pop()
    queries, sealed = seal_initial_plan("Plan a short trip", data, data["queries"])
    assert sealed.get("delivery_plan") is None
    assert "initial_delivery_plan_degraded" in sealed["diagnostic_gaps"]
    assert queries == ["all tourist sights"]
    assert not sealed["decomposition_degraded"]




def test_solution_roundtrips_in_checkpoint_and_branches_keep_it_as_hypothesis():
    from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
    from deeptrace.strategies.model_io import branch_context

    data = solution_payload()
    _, state = seal_initial_plan("Plan a short trip", data, data["queries"])
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(state))
    assert restored["delivery_plan"] == state["delivery_plan"]
    context = branch_context({**request().model_dump(), **restored})
    assert "One compact city route" in " ".join(context["context_notes"])
    assert context["constraints"] == ["Use primary sources"]


@pytest.mark.parametrize("mode", ["workflow", "plan_execute", "multi_agent"])
def test_legacy_results_carry_the_same_selected_solution(mode):
    from deeptrace.strategies.workflow.nodes import finalize_node
    from deeptrace.strategies.plan_execute.nodes import build_finalize_node as pe_final
    from deeptrace.strategies.multi_agent.nodes import build_finalize_node as ma_final

    data = solution_payload()
    _, state = seal_initial_plan("Plan a short trip", data, data["queries"])
    state.update(executed_steps=0, evidence_ids=[])
    finalize = {"workflow": finalize_node, "plan_execute": pe_final(1), "multi_agent": ma_final(1)}[mode]
    outcome = finalize(state)["outcome"]
    assert outcome.delivery_plan == state["delivery_plan"]
    assert outcome.delivery_plan is not None


def test_scope_review_remaps_solution_queries_instead_of_searching_excluded_objects():
    from deeptrace.strategies.scope_review import ScopeReview, _apply_review
    from deeptrace.strategies.delivery_planning import discovery_from_delivery

    data = solution_payload()
    queries, state = seal_initial_plan("Lodging and transit", data, data["queries"])
    review = ScopeReview(requirements=[
        {"id": "r2", "description": "Accommodation reference", "request_excerpt": "Lodging"},
        {"id": "r4", "description": "Transport reference", "request_excerpt": "transit"},
    ], excluded=[{"id": "r1", "reason": "Not requested"}, {"id": "r3", "reason": "Not requested"}])
    _, scoped = _apply_review(review, queries, state, ["Lodging and transit"])
    allocation = discovery_from_delivery(scoped["delivery_plan"], scoped["requirements"], limit=3)
    assert allocation["query_targets"] == {
        "central room dated occupancy price": ["r1"],
        "selected route transport fares and coverage": ["r2"],
    }
