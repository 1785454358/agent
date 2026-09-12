import pytest
from pydantic import ValidationError

from deeptrace.domain import ConversationSummary, Finding, ResearchOutcome, ResearchMode


def test_conversation_summary_is_structured_and_bounded() -> None:
    summary = ConversationSummary(
        topic="Agent Harness",
        user_constraints=["默认简洁回答"],
        established_facts=["研究策略与输出策略分离"],
        referenced_entities={"它": "Agent Harness"},
        unresolved_questions=["Checkpoint 存储"],
        previous_conclusions=["采用 HarnessGraph 加子图"],
    )
    assert summary.referenced_entities["它"] == "Agent Harness"
    with pytest.raises(ValidationError):
        ConversationSummary(topic="x", user_constraints=[str(i) for i in range(51)])


def test_conversation_summary_rejects_an_oversized_topic() -> None:
    with pytest.raises(ValidationError):
        ConversationSummary(topic="x" * 501)


@pytest.mark.parametrize(
    "field_name",
    [
        "user_constraints",
        "established_facts",
        "unresolved_questions",
        "previous_conclusions",
    ],
)
def test_conversation_summary_rejects_an_oversized_list_item(
    field_name: str,
) -> None:
    with pytest.raises(ValidationError):
        ConversationSummary(**{field_name: ["x" * 501]})


def test_conversation_summary_rejects_too_many_referenced_entities() -> None:
    entities = {f"entity-{index}": "value" for index in range(101)}

    with pytest.raises(ValidationError):
        ConversationSummary(referenced_entities=entities)


def test_conversation_summary_rejects_oversized_entity_keys_and_values() -> None:
    with pytest.raises(ValidationError):
        ConversationSummary(referenced_entities={"x" * 101: "value"})
    with pytest.raises(ValidationError):
        ConversationSummary(referenced_entities={"entity": "x" * 501})


def test_research_outcome_contains_findings_by_evidence_reference() -> None:
    outcome = ResearchOutcome(
        mode=ResearchMode.WORKFLOW,
        evidence_ids=["ev-1"],
        findings=[
            Finding(
                id="finding-1",
                claim="Harness 与 Strategy 分离",
                evidence_ids=["ev-1"],
                confidence=0.9,
            )
        ],
        unresolved_gaps=[],
        executed_steps=3,
        termination_reason="completed",
    )
    assert outcome.findings[0].evidence_ids == ["ev-1"]
    assert "source body" not in outcome.model_dump_json()


@pytest.mark.parametrize("field_name", ["id", "claim"])
def test_finding_rejects_empty_required_text(field_name: str) -> None:
    values = {
        "id": "finding-1",
        "claim": "Harness 与 Strategy 分离",
        "evidence_ids": ["ev-1"],
        "confidence": 0.9,
    }
    values[field_name] = ""

    with pytest.raises(ValidationError):
        Finding(**values)


def test_finding_rejects_empty_or_duplicate_evidence_ids() -> None:
    with pytest.raises(ValidationError):
        Finding(id="finding-1", claim="claim", evidence_ids=[], confidence=0.9)
    with pytest.raises(ValidationError):
        Finding(
            id="finding-1",
            claim="claim",
            evidence_ids=["ev-1", "ev-1"],
            confidence=0.9,
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_finding_rejects_confidence_outside_unit_interval(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        Finding(
            id="finding-1",
            claim="claim",
            evidence_ids=["ev-1"],
            confidence=confidence,
        )
