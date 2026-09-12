import pytest
from pydantic import ValidationError

from deeptrace.domain.execution import (
    BudgetSnapshot,
    ErrorCategory,
    ExecutionStatus,
    ResearchOutcome,
    ResearchMode,
    ResponseMode,
    normalize_research_mode,
)


def test_mode_names_are_canonical_and_legacy_names_only_normalize() -> None:
    assert [item.value for item in ResearchMode] == [
        "workflow",
        "plan_execute",
        "multi_agent",
    ]
    assert normalize_research_mode("workflow") is ResearchMode.WORKFLOW
    assert normalize_research_mode("basic") is ResearchMode.WORKFLOW
    assert normalize_research_mode("deep") is ResearchMode.PLAN_EXECUTE
    assert normalize_research_mode("multi_agent") is ResearchMode.MULTI_AGENT
    with pytest.raises(ValueError, match="unknown research mode"):
        normalize_research_mode("agent")


def test_budget_and_outcome_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        BudgetSnapshot(max_model_calls=-1)
    with pytest.raises(ValidationError):
        ResearchOutcome(
            mode=ResearchMode.WORKFLOW,
            evidence_ids=["ev-1", "ev-1"],
            findings=[],
            unresolved_gaps=[],
            executed_steps=1,
            termination_reason="completed",
        )


def test_execution_and_response_values_are_stable() -> None:
    assert ResponseMode.ANSWER.value == "answer"
    assert ResponseMode.REPORT.value == "report"
    assert ErrorCategory.AGENT_RECOVERABLE.value == "agent_recoverable"
    assert ExecutionStatus.INTERRUPTED.value == "interrupted"
