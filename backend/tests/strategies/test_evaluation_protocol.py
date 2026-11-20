"""Decode known field placement mistakes without accepting conflicting claims."""

import json

import pytest
from pydantic import ValidationError

from deeptrace.strategies.evidence_references import parse_reference_evaluation
from deeptrace.strategies.multi_agent.models import ReferenceSupervisorEvaluation
from deeptrace.strategies.plan_execute.models import ReferenceExecutorDecision
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation


def payload(schema):
    value = {
        "findings": [
            {
                "id": "f1",
                "claim": "A fact",
                "confidence": 0.9,
                "supports": [{"ref": "p1"}],
            }
        ],
        "coverage": {
            "items": [
                {
                    "requirement_id": "r1",
                    "status": "covered",
                    "finding_ids": ["f1"],
                    "reason": "Visible text",
                }
            ]
        },
        "unresolved_gaps": [],
        "source_checks": [
            {"source": "s1", "status": "eligible", "reason": "Official text"}
        ],
    }
    if "sufficient" in schema.model_fields:
        value["sufficient"] = True
    else:
        value.update(action="complete", reason="All requirements covered")
    return value


@pytest.mark.parametrize(
    "schema",
    [
        ReferenceWorkflowEvaluation,
        ReferenceExecutorDecision,
        ReferenceSupervisorEvaluation,
    ],
)
def test_relocates_unambiguous_root_fields_then_validates_full_contract(schema):
    expected = payload(schema)
    misplaced = payload(schema)
    for key in set(misplaced) - {"findings", "coverage"}:
        misplaced["coverage"][key] = misplaced.pop(key)
    assert parse_reference_evaluation(
        schema, json.dumps(misplaced)
    ) == schema.model_validate(expected)


@pytest.mark.parametrize(
    "problem", ["conflict", "unknown_field", "invalid_status", "invalid_reference"]
)
def test_placement_repair_cannot_resolve_conflicts_or_relax_field_validation(problem):
    schema = ReferenceSupervisorEvaluation
    value = payload(schema)
    value["coverage"]["action"] = value.pop("action")
    if problem == "conflict":
        value["action"] = "follow_up"
    elif problem == "unknown_field":
        value["coverage"]["approve_all_sources"] = True
    elif problem == "invalid_status":
        value["source_checks"][0]["status"] = "trusted"
    else:
        value["findings"][0]["supports"][0]["ref"] = "p0"
    with pytest.raises(ValidationError):
        parse_reference_evaluation(schema, json.dumps(value))


@pytest.mark.parametrize("raw", ['{"coverage":', "[]", "null"])
def test_malformed_or_non_object_json_stays_a_protocol_failure(raw):
    with pytest.raises(ValidationError):
        parse_reference_evaluation(ReferenceSupervisorEvaluation, raw)


@pytest.mark.parametrize("schema", [ReferenceWorkflowEvaluation, ReferenceExecutorDecision,
                                    ReferenceSupervisorEvaluation])
def test_exact_transport_echo_does_not_discard_an_evidence_assessment(schema):
    value = payload(schema)
    value["type"] = "json_object"
    value["coverage"]["items"][0].update(status="missing", finding_ids=[], reason="Not established")
    if "sufficient" in value:
        value["sufficient"] = False
    else:
        value["action"] = "follow_up" if schema is ReferenceSupervisorEvaluation else "replan"
    result = parse_reference_evaluation(schema, json.dumps(value))
    assert result.coverage.items[0].status == "missing"
    assert result.coverage.items[0].finding_ids == []
    assert result.findings[0].claim == "A fact"
    assert result.findings[0].supports[0].ref == "p1"
    assert result.source_checks[0].status == "eligible"
    if "sufficient" in schema.model_fields:
        assert result.sufficient is False
    else:
        assert result.action == value["action"]


@pytest.mark.parametrize("field,value", [
    ("type", "trusted_document"), ("approve_all_sources", True),
    ("source_checks", [{"source": "s1", "status": "trusted", "reason": "claim"}]),
])
def test_transport_echo_is_not_a_general_unknown_field_or_authority_bypass(field, value):
    data = payload(ReferenceWorkflowEvaluation)
    data["type"] = "json_object"
    data[field] = value
    with pytest.raises(ValidationError):
        parse_reference_evaluation(ReferenceWorkflowEvaluation, json.dumps(data))
