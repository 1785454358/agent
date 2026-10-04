"""Writers consume verified spans and preserve incomplete research status."""

import asyncio
import json

import pytest
from langgraph.errors import NodeCancelledError
from strategies.fixtures import TENANT_ID, build_gateway_fixture

from deeptrace.domain import (
    CoverageAssessment,
    EvidenceSupport,
    Finding,
    ResearchRequirement,
)
from deeptrace.harness.token_budget import TokenBudgetConfig
from deeptrace.responses.graph import build_answer_graph, build_report_graph
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from responses.test_graph import ScriptedModelGateway, _response_input, _seed_evidence


async def _case():
    quote = "Rare supported qualifier."
    body = "generic recovery detail\n\n" * 1500 + quote
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(store, [("https://example.com/doc", "Doc", body)])
    record = await store.get(TENANT_ID, ids[0])
    support = EvidenceSupport(
        evidence_id=record.id,
        version=record.version,
        content_hash=record.content_hash,
        start=body.index(quote),
        end=len(body),
        quote=quote,
    )
    payload = _response_input(ids, question="generic recovery detail")
    payload.constraints = ["preserve exact qualifier"]
    payload.research_outcome = payload.research_outcome.model_copy(
        update={
            "evidence_contract_version": 2,
            "requirements": [
                ResearchRequirement(id="r1", description="Explain qualifier")
            ],
            "findings": [
                Finding(
                    id="f1",
                    claim="A supported conclusion",
                    evidence_ids=ids,
                    confidence=0.9,
                    supports=[support],
                )
            ],
            "coverage": CoverageAssessment(
                items=[
                    {
                        "requirement_id": "r1",
                        "status": "covered",
                        "reason": "literal text",
                        "finding_ids": ["f1"],
                    }
                ]
            ),
        }
    )
    model = ScriptedModelGateway({"responder": json.dumps({"content": "结论 [1]。"})})
    return (
        payload,
        model,
        build_gateway_fixture(model_gateway=model, evidence_store=store),
        body,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("builder", [build_answer_graph, build_report_graph])
async def test_support_beats_generic_query_in_actual_writer_input(builder):
    payload, model, fixture, _ = await _case()
    result = await builder().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    prompt = model.calls[0][1]
    assert "Rare supported qualifier." in prompt
    assert "Explain qualifier" in prompt and '"status": "covered"' in prompt
    assert "A supported conclusion" in prompt
    assert result["outcome"].partial_reason is None
    views = [
        p
        for kind, p in fixture.events.events
        if kind == "evidence.view" and p["stage"] == "response"
    ]
    assert any(p["visibility"] for p in views)
    assert all("text" not in p and "body" not in p for p in views)


@pytest.mark.asyncio
@pytest.mark.parametrize("builder", [build_answer_graph, build_report_graph])
@pytest.mark.parametrize("status", ["missing", "conflicting"])
async def test_valid_citation_does_not_complete_uncovered_research(builder, status):
    payload, model, fixture, _ = await _case()
    payload.research_outcome.coverage.items[0] = (
        payload.research_outcome.coverage.items[0].model_copy(
            update={"status": status, "reason": "scope still uncertain"}
        )
    )
    payload.research_outcome.termination_reason = "insufficient_evidence"
    result = await builder().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert result["outcome"].partial_reason == "insufficient_evidence"
    assert "scope still uncertain" in model.calls[0][1]
    assert result["outcome"].cited_evidence_ids == payload.active_evidence_ids


@pytest.mark.asyncio
async def test_stale_support_is_not_presented_as_an_accepted_fact():
    payload, model, fixture, _ = await _case()
    payload.research_outcome.findings[0].supports[0] = (
        payload.research_outcome.findings[0]
        .supports[0]
        .model_copy(update={"content_hash": "wrong"})
    )
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert "A supported conclusion" not in model.calls[0][1]
    assert result["outcome"].partial_reason == "invalid_finding_support"


@pytest.mark.asyncio
async def test_token_dropped_source_drops_its_finding_and_cannot_certify_citation():
    payload, model, fixture, _ = await _case()
    budget = TokenBudgetConfig(
        context_tokens=900, output_reserve_tokens=0, safety_tokens=0
    )
    result = await build_answer_graph(budget).ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert "Rare supported qualifier." not in model.calls[0][1]
    assert "A supported conclusion" not in model.calls[0][1]
    assert result["outcome"].partial_reason is not None
    assert result["outcome"].cited_evidence_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize("builder", [build_answer_graph, build_report_graph])
async def test_writer_overflow_accounts_for_mandatory_task_envelope(builder):
    payload, model, fixture, _ = await _case()
    payload.question = "scope " * 300
    budget = TokenBudgetConfig(
        context_tokens=900, output_reserve_tokens=0, safety_tokens=0
    )
    result = await builder(budget).ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert model.calls == []
    assert result["grounding_issue"] == "response_context_limit"
    assert result["outcome"].partial_reason is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "read_body"])
async def test_writer_preserves_healthy_source_when_a_sibling_store_read_fails(
    operation, monkeypatch
):
    payload, model, fixture, _ = await _case()
    bad_ids = await _seed_evidence(
        fixture.evidence_store,
        [("https://example.com/broken", "Broken", "unavailable detail")],
    )
    payload.active_evidence_ids.extend(bad_ids)
    original = getattr(fixture.evidence_store, operation)

    async def faulted_read(tenant, identity):
        if identity == bad_ids[0]:
            raise RuntimeError("private infrastructure diagnostic")
        return await original(tenant, identity)

    monkeypatch.setattr(fixture.evidence_store, operation, faulted_read)
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert result["outcome"].cited_evidence_ids == [payload.active_evidence_ids[0]]
    assert "Rare supported qualifier." in model.calls[0][1]
    assert "unavailable detail" not in model.calls[0][1]
    assert "private infrastructure diagnostic" not in model.calls[0][1]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "read_body"])
async def test_optional_source_io_never_swallows_cancellation(operation, monkeypatch):
    payload, model, fixture, _ = await _case()

    async def cancelled_read(tenant, identity):
        raise asyncio.CancelledError

    monkeypatch.setattr(fixture.evidence_store, operation, cancelled_read)
    with pytest.raises(NodeCancelledError):
        await build_answer_graph().ainvoke(
            {"response_input": payload}, context=fixture.context
        )
    assert model.calls == []


@pytest.mark.asyncio
async def test_forged_negative_coordinate_is_rejected_even_if_python_slice_matches():
    from deeptrace.tools.evidence_views import select_supported_passages

    payload, _, fixture, body = await _case()
    record = await fixture.evidence_store.get(TENANT_ID, payload.active_evidence_ids[0])
    support = (
        payload.research_outcome.findings[0]
        .supports[0]
        .model_copy(
            update={"start": -len("Rare supported qualifier."), "end": len(body)}
        )
    )
    passages = select_supported_passages(
        record, body, [support], question="generic recovery detail", limit=200
    )
    assert all("Rare supported qualifier." not in p.text for p in passages)


def test_invisible_first_source_does_not_renumber_second_source_before_validation():
    from deeptrace.domain import ResponseMode
    from deeptrace.responses.citations import validate_citations
    from deeptrace.responses.models import ResponseDraft

    draft = ResponseDraft(
        response_mode=ResponseMode.ANSWER, content="Second fact [2]; hidden [1]."
    )
    result = validate_citations(
        draft, loaded_evidence_ids=["first", "second"], visible_evidence_ids=["second"]
    )
    assert result.cited_evidence_ids == ["second"]
    assert result.content == "Second fact [1]; hidden ."


@pytest.mark.asyncio
async def test_application_does_not_complete_a_forged_completed_but_missing_contract():
    from deeptrace.domain import ResearchMode, ResponseMode, ResponseOutcome
    from deeptrace.harness.graph import _finalize_turn
    from deeptrace.harness.state import new_turn

    payload, _, _, _ = await _case()
    payload.research_outcome.coverage.items[0] = (
        payload.research_outcome.coverage.items[0].model_copy(
            update={"status": "missing"}
        )
    )
    turn = new_turn("run-1", "question", ResearchMode.WORKFLOW)
    turn["research_outcome"] = payload.research_outcome
    turn["response_outcome"] = ResponseOutcome(
        response_mode=ResponseMode.ANSWER,
        content="Answer [1].",
        citations=[{"evidence_id": payload.active_evidence_ids[0], "marker": "[1]"}],
        cited_evidence_ids=payload.active_evidence_ids,
    )
    result = _finalize_turn({"turn": turn})
    assert result["turn"]["status"] == "partial"
