import pytest
from pydantic import ValidationError

from deeptrace.domain.evidence import Finding
from deeptrace.domain.research import ResearchTopicOutcome, TopicStepError
from deeptrace.strategies.workflow.models import QueryPlan, WorkflowEvaluation
from deeptrace.strategies.workflow.nodes import (
    filter_findings,
    parse_query_plan,
    topic_error_gaps,
)


def test_query_plan_is_strict_unique_and_bounded() -> None:
    plan = QueryPlan(queries=["a", "b", "a"])
    assert plan.queries == ["a", "b"]

    with pytest.raises(ValidationError):
        QueryPlan(queries=[])
    with pytest.raises(ValidationError):
        QueryPlan(queries=[str(index) for index in range(11)])
    with pytest.raises(ValidationError):
        QueryPlan(queries=["ok"], unexpected=1)


def test_workflow_evaluation_is_strict_and_bounded() -> None:
    evaluation = WorkflowEvaluation(
        findings=[],
        unresolved_gaps=["更多来源"],
        sufficient=False,
    )
    assert evaluation.sufficient is False
    with pytest.raises(ValidationError):
        WorkflowEvaluation(findings=[], unresolved_gaps=[], sufficient="maybe")
    with pytest.raises(ValidationError):
        WorkflowEvaluation(
            findings=[],
            unresolved_gaps=["g" * 600],
            sufficient=True,
        )
    with pytest.raises(ValidationError):
        WorkflowEvaluation(findings=[], unresolved_gaps=[], sufficient=True, extra=1)


def test_parse_query_plan_falls_back_to_the_user_question() -> None:
    assert parse_query_plan('{"queries": ["a", "b"]}', limit=3, fallback="question") == [
        "a",
        "b",
    ]
    assert parse_query_plan(
        '```json\n{"queries": ["a"]}\n```', limit=3, fallback="question"
    ) == ["a"]

    assert parse_query_plan("not json", limit=3, fallback="fallback question") == [
        "fallback question"
    ]
    assert parse_query_plan('{"queries": []}', limit=3, fallback="fallback") == [
        "fallback"
    ]
    assert parse_query_plan(
        '{"queries": ["a", "a", "b", "c", "d"]}', limit=3, fallback="fallback"
    ) == ["a", "b", "c"]
    assert parse_query_plan(
        '{"queries": ["a", "' + "x" * 1_200 + '"]}', limit=3, fallback="fallback"
    ) == ["a"]


def test_filter_findings_drops_unknown_evidence_references() -> None:
    valid = Finding(
        id="finding-1",
        claim="supported",
        evidence_ids=["evidence-1"],
        confidence=0.9,
    )
    invalid = Finding(
        id="finding-2",
        claim="hallucinated",
        evidence_ids=["evidence-unknown"],
        confidence=0.9,
    )

    kept = filter_findings([valid, invalid], allowed_evidence_ids={"evidence-1"})

    assert kept == [valid]
    assert filter_findings([invalid], allowed_evidence_ids=set()) == []


def test_topic_error_gaps_are_stable_and_query_scoped() -> None:
    outcome = ResearchTopicOutcome(
        query="second query",
        evidence_ids=[],
        attempted_urls=[],
        errors=[
            TopicStepError(stage="search", target="", code="no_search_results"),
            TopicStepError(
                stage="fetch", target="https://example.com/a", code="empty_page"
            ),
        ],
        executed_steps=2,
    )

    gaps = topic_error_gaps(outcome)

    assert gaps == [
        "topic[second query] search::no_search_results",
        "topic[second query] fetch:https://example.com/a:empty_page",
    ]
    assert topic_error_gaps(
        ResearchTopicOutcome(
            query="q",
            evidence_ids=["evidence-1"],
            attempted_urls=["https://example.com/a"],
            errors=[],
            executed_steps=2,
        )
    ) == []
