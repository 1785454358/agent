"""The host rejects infeasible or incomplete plans before execution."""

from deeptrace.domain import ResearchRequirement
from deeptrace.research import (
    ContractBudget,
    PlanIssueSeverity,
    PlanTask,
    ResearchAmbiguity,
    ResearchContract,
    ResearchPlan,
    TaskBudget,
    review_plan,
)


ALLOWED = {"search_web", "fetch_page", "read_evidence"}


def _contract(**changes) -> ResearchContract:
    values = {
        "run_id": "run-1",
        "goal": "Answer the research question",
        "requirements": (
            ResearchRequirement(id="r1", description="First requirement"),
            ResearchRequirement(id="r2", description="Second requirement"),
        ),
        "budget": ContractBudget(max_model_calls=20, finishing_calls=3),
    }
    values.update(changes)
    return ResearchContract.model_validate(values)


def _task(task_id: str, **changes) -> PlanTask:
    values = {
        "id": task_id,
        "type": "discover",
        "objective": f"Research task {task_id}",
        "in_scope": "Assigned hypothesis",
        "out_of_scope": "Final answer",
        "requirement_ids": ("r1",),
        "capabilities": ("search_web",),
        "query_seeds": (f"query {task_id}",),
        "expected_output": "Supported facts",
        "acceptance": ("One verified support",),
        "budget": TaskBudget(max_calls=3, max_pages=2),
    }
    values.update(changes)
    return PlanTask.model_validate(values)


def _plan(*tasks: PlanTask, **changes) -> ResearchPlan:
    values = {
        "plan_id": "plan-1",
        "run_id": "run-1",
        "contract_revision": 1,
        "tasks": tasks or (_task("t1"),),
        "stop_conditions": ("All acceptance requirements are covered",),
    }
    values.update(changes)
    return ResearchPlan.model_validate(values)


def _codes(review) -> set[str]:
    return {issue.code for issue in review.issues}


def test_valid_plan_is_accepted_with_bounded_effort() -> None:
    review = review_plan(
        _plan(
            _task("t1", requirement_ids=("r1",)),
            _task(
                "t2",
                requirement_ids=("r2",),
                capabilities=("read_evidence",),
                depends_on=("t1",),
            ),
        ),
        _contract(),
        allowed_capabilities=ALLOWED,
    )
    assert review.accepted
    assert review.errors == ()
    assert review.covered_requirement_ids == ("r1", "r2")
    assert review.uncovered_requirement_ids == ()
    assert review.estimated_model_calls == 6
    assert review.estimated_pages == 4


def test_unknown_requirement_uncovered_requirement_and_bad_capability_are_errors() -> None:
    review = review_plan(
        _plan(_task("t1", requirement_ids=("r2",), capabilities=("unknown_tool",))),
        _contract(),
        allowed_capabilities=ALLOWED,
    )
    assert not review.accepted
    assert {"uncovered_requirements", "unknown_capability"} <= _codes(review)


def test_plan_cannot_drop_contract_requirements_or_exceed_budget() -> None:
    contract = _contract(
        budget=ContractBudget(max_model_calls=6, finishing_calls=2),
    )
    review = review_plan(
        _plan(
            _task("t1", requirement_ids=("r1",), budget=TaskBudget(max_calls=3)),
            _task("t2", requirement_ids=("r2",), budget=TaskBudget(max_calls=3)),
        ),
        contract,
        allowed_capabilities=ALLOWED,
    )
    assert not review.accepted
    assert "budget_infeasible" in _codes(review)
    assert "uncovered_requirements" not in _codes(review)


def test_contract_identity_revision_and_clarification_are_enforced() -> None:
    review = review_plan(
        _plan(_task("t1", requirement_ids=("r1", "r2"))),
        _contract(run_id="run-2", revision=1),
        allowed_capabilities=ALLOWED,
    )
    assert "run_identity_mismatch" in _codes(review)

    clarified = _contract(
        risk="high",
        ambiguity=ResearchAmbiguity(level="high", questions=("Which edition?",)),
    )
    review = review_plan(
        _plan(_task("t1", requirement_ids=("r1", "r2"))),
        clarified,
        allowed_capabilities=ALLOWED,
    )
    assert "clarification_required" in _codes(review)

    review = review_plan(
        _plan(_task("t1", requirement_ids=("r1", "r2")), contract_revision=2),
        _contract(),
        allowed_capabilities=ALLOWED,
    )
    assert "contract_revision_mismatch" in _codes(review)


def test_missing_contract_requirements_and_task_limit_are_errors() -> None:
    contract = ResearchContract(run_id="run-1", goal="Answer")
    review = review_plan(
        _plan(_task("t1"), _task("t2")),
        contract,
        allowed_capabilities=ALLOWED,
        max_tasks=1,
    )
    assert {"contract_has_no_requirements", "task_limit_exceeded"} <= _codes(review)


def test_duplicate_queries_are_warnings_not_blockers() -> None:
    review = review_plan(
        _plan(
            _task("t1", requirement_ids=("r1",), query_seeds=(" Same   Query ",)),
            _task("t2", requirement_ids=("r2",), query_seeds=("same query",)),
        ),
        _contract(),
        allowed_capabilities=ALLOWED,
    )
    assert review.accepted
    assert any(
        issue.code == "duplicate_query"
        and issue.severity is PlanIssueSeverity.WARNING
        for issue in review.issues
    )
