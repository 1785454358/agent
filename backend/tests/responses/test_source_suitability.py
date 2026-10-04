"""Rejected sources cannot return through writer fallback or citation numbering."""

import json

import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.responses.evidence import assemble_response_materials
from deeptrace.responses.graph import build_answer_graph
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from responses.test_graph import ScriptedModelGateway, _response_input, _seed_evidence


@pytest.mark.asyncio
async def test_rejected_source_is_absent_from_writer_prompt_and_citations():
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store,
        [
            ("https://example.com/v2/tasks", "v2", "Cleanup is required."),
            ("https://example.com/v9/tasks", "v9", "Rejected source fact."),
        ],
    )
    payload = _response_input(ids, question="Explain cleanup using v2 only.")
    payload.research_outcome = payload.research_outcome.model_copy(
        update={"source_eligibility": {ids[0]: "eligible", ids[1]: "ineligible"}}
    )
    model = ScriptedModelGateway(
        {"responder": json.dumps({"content": "需要清理 [1]。"})}
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert "https://example.com/v2/tasks" in model.calls[0][1]
    assert "https://example.com/v9/tasks" not in model.calls[0][1]
    assert "Rejected source fact" not in model.calls[0][1]
    assert [r.id for r in result["loaded_evidence"]] == [ids[0]]


@pytest.mark.asyncio
async def test_direct_material_assembly_cannot_bypass_source_admission():
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/v9/tasks", "v9", "Rejected source fact.")]
    )
    payload = _response_input(ids)
    payload.research_outcome = payload.research_outcome.model_copy(
        update={"source_eligibility": {}}
    )
    fixture = build_gateway_fixture(evidence_store=store)
    records = await store.get_many(fixture.context.workspace_id, ids)
    materials = await assemble_response_materials(
        fixture.context, payload, records, 3000
    )
    assert materials.sources == []
    assert materials.findings == []
