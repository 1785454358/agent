import pytest
from pydantic import ValidationError

from deeptrace.domain import (
    CitationRef,
    ResearchOutcome,
    ResearchMode,
    ResponseInput,
    ResponseMode,
    ResponseOutcome,
)


def _research_outcome() -> ResearchOutcome:
    return ResearchOutcome(
        mode=ResearchMode.WORKFLOW,
        evidence_ids=["evidence-1"],
        findings=[],
        unresolved_gaps=[],
        executed_steps=1,
        termination_reason="completed",
    )


def test_response_input_rejects_unknown_fields_and_duplicate_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ResponseInput(
            question="What changed?",
            response_mode=ResponseMode.ANSWER,
            research_outcome=_research_outcome(),
            active_evidence_ids=["evidence-1"],
            unexpected="value",
        )

    with pytest.raises(ValidationError, match="must be unique"):
        ResponseInput(
            question="What changed?",
            response_mode=ResponseMode.ANSWER,
            research_outcome=_research_outcome(),
            active_evidence_ids=["evidence-1", "evidence-1"],
        )


def test_response_input_bounds_active_evidence_ids() -> None:
    with pytest.raises(ValidationError):
        ResponseInput(
            question="What changed?",
            response_mode=ResponseMode.ANSWER,
            research_outcome=_research_outcome(),
            active_evidence_ids=[
                f"evidence-{index}" for index in range(10_000)
            ],
        )


def test_response_outcome_rejects_duplicate_and_unbounded_citations() -> None:
    duplicate = CitationRef(evidence_id="evidence-1", marker="[1]")
    with pytest.raises(ValidationError, match="citation evidence_ids must be unique"):
        ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="Supported answer.",
            citations=[duplicate, duplicate],
            cited_evidence_ids=["evidence-1"],
        )

    with pytest.raises(ValidationError):
        ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="Supported answer.",
            citations=[
                CitationRef(evidence_id=f"evidence-{index}", marker=f"[{index}]")
                for index in range(10_000)
            ],
            cited_evidence_ids=[
                f"evidence-{index}" for index in range(10_000)
            ],
        )


def test_response_outcome_bounds_content() -> None:
    with pytest.raises(ValidationError):
        ResponseOutcome(
            response_mode=ResponseMode.REPORT,
            content="x" * 1_000_000,
            citations=[],
            cited_evidence_ids=[],
            partial_reason="no_sources",
        )


def test_response_outcome_requires_citation_references_to_match() -> None:
    with pytest.raises(ValidationError, match="must match citation evidence_ids"):
        ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="Supported answer.",
            citations=[CitationRef(evidence_id="evidence-1", marker="[1]")],
            cited_evidence_ids=["evidence-2"],
        )


def test_complete_response_requires_at_least_one_evidence_reference() -> None:
    with pytest.raises(ValidationError, match="complete responses require evidence"):
        ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="Unsupported answer.",
            citations=[],
            cited_evidence_ids=[],
        )


def test_response_outcome_accepts_a_stable_partial_reason() -> None:
    partial = ResponseOutcome(
        response_mode=ResponseMode.ANSWER,
        content="No supported answer is available.",
        citations=[],
        cited_evidence_ids=[],
        partial_reason="no_sources",
    )
    assert partial.partial_reason == "no_sources"
