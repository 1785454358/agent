"""Grounded v3 writing must not turn validation failures into corpus absence."""

import json

import pytest

from deeptrace.responses.graph import build_answer_graph
from responses.test_supported_findings import _case


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [2, 3])
async def test_historical_and_new_supported_results_use_verified_writer_material(
    version,
):
    payload, model, fixture, _ = await _case()
    payload.research_outcome.evidence_contract_version = version
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert "Rare supported qualifier." in model.calls[0][1]
    assert "A supported conclusion" in model.calls[0][1]
    assert result["outcome"].partial_reason is None


@pytest.mark.asyncio
async def test_invalid_reference_cause_is_separate_from_fact_coverage_in_writer_input():
    payload, model, fixture, _ = await _case()
    payload.research_outcome.evidence_contract_version = 3
    payload.research_outcome.termination_reason = "insufficient_evidence"
    payload.research_outcome.coverage.items[0].status = "missing"
    payload.research_outcome.coverage.items[
        0
    ].reason = "unsupported_requirement_coverage"
    payload.research_outcome.coverage.items[0].finding_ids = []
    payload.research_outcome.unresolved_gaps = [
        "r1:missing:unsupported_requirement_coverage",
        "diagnostic:invalid_support_reference",
    ]
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    prompt = model.calls[0][1]
    context = json.JSONDecoder().raw_decode(
        prompt.split("封存研究需求与当前覆盖", 1)[1].split("\n", 1)[1]
    )[0]
    assert context["coverage"]["items"][0]["status"] == "missing"
    assert context["evidence_limitations"]["diagnostics"] == [
        "invalid_support_reference"
    ]
    assert (
        context["evidence_limitations"]["absence_scope"] == "current_visible_materials"
    )
    assert context["current_gaps"] == ["r1:missing:unsupported_requirement_coverage"]
    assert result["outcome"].partial_reason == "insufficient_evidence"
