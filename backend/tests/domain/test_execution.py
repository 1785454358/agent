import pytest
from pydantic import ValidationError

from deeptrace.domain.execution import (
    BudgetSnapshot,
    ErrorCategory,
    ExecutionStatus,
    ResearchOutcome,
    ResearchProfile,
    ResponseProfile,
    normalize_research_profile,
)


def test_profile_names_are_canonical_and_legacy_names_only_normalize() -> None:
    assert [item.value for item in ResearchProfile] == [
        "workflow",
        "plan_execute",
        "multi_agent",
    ]
    assert normalize_research_profile("workflow") is ResearchProfile.WORKFLOW
    assert normalize_research_profile("basic") is ResearchProfile.WORKFLOW
    assert normalize_research_profile("deep") is ResearchProfile.PLAN_EXECUTE
    assert normalize_research_profile("multi_agent") is ResearchProfile.MULTI_AGENT
    with pytest.raises(ValueError, match="unknown research profile"):
        normalize_research_profile("agent")


def test_budget_and_outcome_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot(max_model_calls=-1)
    with pytest.raises(ValidationError):
        ResearchOutcome(
            profile=ResearchProfile.WORKFLOW,
            evidence_ids=["ev-1", "ev-1"],
            findings=[],
            unresolved_gaps=[],
            executed_steps=1,
            termination_reason="completed",
        )


def test_execution_and_response_values_are_stable() -> None:
    assert ResponseProfile.ANSWER.value == "answer"
    assert ResponseProfile.REPORT.value == "report"
    assert ErrorCategory.AGENT_RECOVERABLE.value == "agent_recoverable"
    assert ExecutionStatus.INTERRUPTED.value == "interrupted"
