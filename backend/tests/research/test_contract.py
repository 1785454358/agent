"""The research contract is bounded, versioned and independent of a strategy."""

import pytest
from pydantic import ValidationError

from deeptrace.domain import ResearchInput, ResearchRequirement
from deeptrace.research import (
    ContractBudget,
    ResearchAmbiguity,
    ResearchContract,
    SourcePolicy,
)


def _contract(**changes) -> ResearchContract:
    return ResearchContract.model_validate(
        {"run_id": "run-1", "goal": "Explain the target", **changes}
    )


def test_revisions_require_parent_and_reason() -> None:
    original = _contract()
    revised = original.with_requirements(
        (ResearchRequirement(id="r1", description="A verifiable requirement"),),
        reason="Planner proposed the first acceptance criterion",
    )
    assert original.requirements == ()
    assert original.revision == 1
    assert revised.revision == 2
    assert revised.parent_revision == 1
    assert revised.requirements[0].id == "r1"


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": 2},
        {"revision": 2, "parent_revision": 1, "revision_reason": "reason"},
        {"revision": 2, "parent_revision": 2, "revision_reason": "reason"},
        {"revision": 1, "parent_revision": 1},
        {"parent_revision": 1},
        {"requirements": [
            {"id": "r1", "description": "first"},
            {"id": "r1", "description": "duplicate"},
        ]},
        {"oracle_answer": "not allowed"},
    ],
)
def test_invalid_contracts_are_rejected(changes) -> None:
    with pytest.raises(ValidationError):
        _contract(**changes)


def test_high_risk_ambiguity_requires_a_clarification_question() -> None:
    with pytest.raises(ValidationError):
        _contract(risk="high", ambiguity={"level": "high"})
    contract = _contract(
        risk="high",
        ambiguity=ResearchAmbiguity(level="high", questions=("Which edition?",)),
    )
    assert contract.requires_clarification
    assert not _contract(risk="low").requires_clarification


def test_budget_reserves_response_calls_and_policy_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ContractBudget(max_model_calls=3, finishing_calls=3)
    with pytest.raises(ValidationError):
        SourcePolicy(domains=("example.com", "example.com"))
    contract = _contract(
        source_policy=SourcePolicy(mode="corpus", domains=("docs.python.org",)),
        budget=ContractBudget(max_model_calls=30, max_input_tokens=200_000),
    )
    assert contract.budget.finishing_calls == 3
    assert contract.source_policy.mode == "corpus"


def test_legacy_research_input_projection_does_not_invent_requirements() -> None:
    research_input = ResearchInput(
        run_id="run-1",
        thread_id="thread-1",
        question="Compare two documented behaviors",
        current_date="2026-11-13",
        timezone="Asia/Shanghai",
    )
    contract = ResearchContract.from_research_input(research_input)
    assert contract.goal == research_input.question
    assert contract.requirements == ()
    assert contract.revision == 1
    assert not contract.requires_clarification


@pytest.mark.parametrize("restored", [False, True])
def test_requirement_snapshot_cannot_be_changed_without_a_contract_revision(restored):
    from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
    requirement = ResearchRequirement(id="r1", description="Original criterion")
    contract = _contract(requirements=[requirement])
    if restored:
        serializer = create_harness_checkpoint_serializer()
        contract = serializer.loads_typed(serializer.dumps_typed(contract))
    with pytest.raises(ValidationError, match="frozen"):
        contract.requirements[0].description = "Silently weakened criterion"
    assert contract.requirements[0].description == "Original criterion"
    revised = contract.with_requirements(
        (ResearchRequirement(id="r1", description="Explicitly revised criterion"),),
        reason="User changed the requested scope",
    )
    assert revised.revision == 2
    assert contract.requirements[0].description == "Original criterion"
