"""The adapter turns legacy planner output into a reviewed, executable plan."""

import pytest

from deeptrace.domain import ResearchRequirement
from deeptrace.research import (
    ContractBudget,
    ExecutionShape,
    build_contract_and_plan,
    decide_execution,
    review_plan,
)


def _requirements():
    return (
        ResearchRequirement(id="r1", description="First fact"),
        ResearchRequirement(id="r2", description="Second fact"),
    )


def test_adapter_builds_contract_and_fanout_plan() -> None:
    contract, plan = build_contract_and_plan(
        run_id="run-1",
        question="Compare two documented behaviors",
        requirements=_requirements(),
        queries=["query one", "query two"],
        query_targets={"query one": ["r1"], "query two": ["r2"]},
        budget=ContractBudget(max_model_calls=20, finishing_calls=3),
    )
    assert [task.id for task in plan.tasks] == ["t1", "t2"]
    assert plan.tasks[0].requirement_ids == ("r1",)
    assert plan.tasks[1].requirement_ids == ("r2",)
    assert all(not task.depends_on for task in plan.tasks)

    review = review_plan(
        plan,
        contract,
        allowed_capabilities={"search_web", "fetch_page", "read_evidence"},
    )
    assert review.accepted
    decision = decide_execution(plan, review)
    assert decision.shape is ExecutionShape.FANOUT
    assert decision.max_parallel == 2


def test_adapter_defaults_unmapped_queries_to_every_requirement() -> None:
    _, plan = build_contract_and_plan(
        run_id="run-1",
        question="Explain",
        requirements=_requirements(),
        queries=["only query"],
    )
    assert plan.tasks[0].requirement_ids == ("r1", "r2")


def test_adapter_preserves_source_policy() -> None:
    contract, _ = build_contract_and_plan(
        run_id="run-1",
        question="Explain",
        requirements=_requirements(),
        queries=["query"],
        source_policy="research_results",
        source_domains=["docs.python.org"],
        publication_years=[2025],
    )
    assert contract.source_policy.mode == "research_results"
    assert contract.source_policy.domains == ("docs.python.org",)
    assert contract.source_policy.publication_years == (2025,)


@pytest.mark.parametrize(
    "requirements,queries,targets",
    [
        ((), ["query"], None),
        (_requirements(), [], None),
        (_requirements(), ["query"], {"query": ["r9"]}),
    ],
)
def test_adapter_rejects_missing_or_inconsistent_inputs(
    requirements, queries, targets
) -> None:
    with pytest.raises(ValueError):
        build_contract_and_plan(
            run_id="run-1",
            question="Explain",
            requirements=requirements,
            queries=queries,
            query_targets=targets,
        )


@pytest.mark.parametrize("targets", [
    {"gap query": []},
    {"gap query": ["r2", "r2"]},
    {"gap query": ["r9"]},
    {"another query": ["r2"]},
])
def test_discovery_tasks_reject_ambiguous_or_invalid_gap_assignments(targets):
    from deeptrace.research.adapters import build_discovery_tasks
    with pytest.raises(ValueError):
        build_discovery_tasks(
            requirements=_requirements(), queries=["gap query"], query_targets=targets,
        )


def test_discovery_tasks_do_not_expand_a_gap_into_all_requirements():
    from deeptrace.research.adapters import build_discovery_tasks
    tasks = build_discovery_tasks(
        requirements=_requirements(), queries=["gap query"],
        query_targets={"gap query": ["r2"]}, first_task_number=3,
    )
    assert len(tasks) == 1
    assert tasks[0].id == "t3"
    assert tasks[0].requirement_ids == ("r2",)


def test_gap_revision_replaces_failed_work_and_preserves_contract_and_history():
    from deeptrace.research.planning import revise_research_plan
    contract, old = build_contract_and_plan(
        run_id="run-1", question="Compare", requirements=_requirements(),
        queries=["first", "second"], query_targets={"first": ["r1"], "second": ["r2"]},
        source_policy="research_results", source_domains=["example.com"],
        publication_years=[2026],
    )
    state = {"run_id": "run-1", "question": "Compare", "contract": contract,
             "plan": old, "plan_history": [], "round_count": 1,
             "queries": ["first", "second"], "recovery_queries": ["repair first"],
             "supplement_targets": {"repair first": ["r1"]},
             "task_results": {"t1": {"status": "failed"}, "t2": {"status": "completed"}}}
    result = revise_research_plan(state)
    assert result["plan"].plan_id == old.plan_id
    assert result["plan"].revision == 2
    assert result["plan"].parent_revision == 1
    assert result["plan"].contract_revision == contract.revision
    assert [(task.id, task.requirement_ids) for task in result["plan"].tasks] == [
        ("t2", ("r2",)), ("t3", ("r1",))]
    assert result["plan_history"] == [old]
    assert old.revision == 1
    assert old.tasks[0].id == "t1"
    assert state["contract"] is contract
    assert state["plan_history"] == []


def test_legal_long_run_ids_produce_bounded_distinct_plan_identities():
    run_ids = ["r" * 128, "r" * 127 + "s"]
    plan_ids = []
    for run_id in run_ids:
        contract, plan = build_contract_and_plan(
            run_id=run_id, question="Explain", requirements=_requirements(), queries=["query"],
        )
        assert contract.run_id == run_id
        assert plan.run_id == run_id
        assert len(plan.plan_id) <= 128
        plan_ids.append(plan.plan_id)
    assert plan_ids[0] != plan_ids[1]
