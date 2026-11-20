import pytest


@pytest.mark.parametrize("detail,expected", [
    ("completed", "completed"),
    ("workflow_completed", "completed"),
    ("max_iterations", "iteration_limit"),
    ("max_replans_reached", "planning_limit"),
    ("max_follow_ups_reached", "planning_limit"),
    ("no_sources", "insufficient_evidence"),
    ("budget_exhausted:input_tokens", "budget_exhausted"),
    ("cancelled", "cancelled"),
    ("worker_error", "runtime_error"),
    ("citation_invalid", "response_error"),
    ("answer_review_incomplete", "response_error"),
    ("answer_review_unavailable", "response_error"),
    ("generation_failed", "response_error"),
    ("response_context_limit", "context_limit"),
    ("response_evidence_context_limit", "context_limit"),
    ("new_unknown_reason", "unknown"),
    ("", "unknown"),
])
def test_legacy_details_normalize_without_inventing_success(detail, expected):
    from deeptrace.domain.run import normalize_finish_reason

    assert normalize_finish_reason(detail).value == expected


def test_branch_result_uses_the_shared_finish_vocabulary():
    from deeptrace.domain.agent import AgentOutcome

    result = AgentOutcome(status="partial", stop_reason="iteration_limit")
    assert result.finish_reason == "iteration_limit"
    assert result.stop_reason == "iteration_limit"
