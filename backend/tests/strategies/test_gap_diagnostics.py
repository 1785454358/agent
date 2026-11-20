import pytest

from deeptrace.domain import ResearchTopicOutcome
from deeptrace.strategies.evidence_evaluation import final_evidence_gaps
from deeptrace.strategies.gap_diagnostics import acquisition_diagnostics


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (
            {"query": "q", "errors": [{"stage": "search", "code": "search_failed"}]},
            "discovery",
        ),
        (
            {
                "query": "q",
                "research_finding_diagnostics": ["batch_acquisition_incomplete"],
            },
            "discovery",
        ),
        (
            {
                "query": "q",
                "errors": [{"stage": "fetch", "code": "insufficient_content"}],
            },
            "fetch",
        ),
        (
            {"query": "q", "errors": [{"stage": "read", "code": "evidence_no_match"}]},
            "read",
        ),
        (
            {
                "query": "q",
                "research_finding_diagnostics": ["synthesis_window_omitted:4"],
            },
            "context",
        ),
    ],
)
def test_acquisition_diagnostics_name_the_failed_stage_and_recovery(outcome, expected):
    state = {"topic_outcomes": [ResearchTopicOutcome.model_validate(outcome)]}
    rows = acquisition_diagnostics(state)
    assert expected in {row["stage"] for row in rows}
    assert all(row["next_action"] for row in rows)


def test_reference_failure_is_not_classified_as_missing_source():
    rows = acquisition_diagnostics({"diagnostic_gaps": ["invalid_support_reference"]})
    assert [row["stage"] for row in rows] == ["validation"]
    assert "discovery" not in {row["stage"] for row in rows}


def test_final_delivery_keeps_causes_as_diagnostics_not_additional_requirements():
    result = final_evidence_gaps(
        {
            "unresolved_gaps": ["r1:missing:Need the cancellation condition"],
            "diagnostic_gaps": ["synthesis_window_omitted:4"],
        }
    )
    assert result == [
        "r1:missing:Need the cancellation condition",
        "diagnostic:synthesis_window_omitted:4",
    ]
