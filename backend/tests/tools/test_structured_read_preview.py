"""Catch semantically partial JSON fitting and anchors from unrelated prefixes."""

import json

import pytest
from strategies.fixtures import TENANT_ID, build_gateway_fixture

from deeptrace.harness.read_anchors import capture_read_anchors
from deeptrace.harness.research_findings import number_read_preview
from deeptrace.tools.evidence_read import _fit_preview
from deeptrace.tools.evidence_views import make_evidence_passage
from deeptrace.tools.policy import EvidenceAuthorization
from tools.test_evidence_read import _draft, _read


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["query", "full"])
async def test_query_json_fitting_omits_whole_escaped_group_not_its_tail(strategy):
    fixture = build_gateway_fixture()
    body = "If special_flag is false, " + '\\"' * 1100 + " operations continue."
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft(body))
    preview = _fit_preview(
        record,
        body,
        (make_evidence_passage(record, body, 0, len(body)),),
        strategy=strategy,
    )
    payload = json.loads(preview)
    assert payload["passages"] == []
    assert payload["selection"]["omitted"] is True
    assert payload["selection"]["reason"] == "preview_budget_omitted"
    assert len(preview) <= 4000
    numbered, refs, _ = number_read_preview(preview, {})
    anchors, _ = capture_read_anchors(numbered, record.id)
    assert refs == {} and anchors == []


@pytest.mark.asyncio
async def test_full_short_read_does_not_claim_keyword_relevance():
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft())
    result = await _read(
        fixture,
        record.id,
        grants=EvidenceAuthorization(frozenset([record.id])),
        arguments={"query": "quasar"},
    )
    payload = json.loads(result.preview)
    assert payload["selection"]["strategy"] == "full"
    assert payload["selection"]["found"] is None
    assert payload["passages"][0]["text"] == "Store keeps cross-thread facts."


@pytest.mark.asyncio
async def test_no_match_query_has_diagnostic_and_no_read_anchor():
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(
        TENANT_ID, _draft("Ordinary background.\n\n" * 100)
    )
    result = await _read(
        fixture,
        record.id,
        grants=EvidenceAuthorization(frozenset([record.id])),
        arguments={"query": "quasar"},
    )
    assert result.ok
    payload = json.loads(result.preview)
    assert payload["passages"] == []
    assert payload["selection"]["reason"] == "query_no_match"
    assert payload["selection"]["found"] is False
    numbered, refs, _ = number_read_preview(result.preview, {})
    anchors, _ = capture_read_anchors(numbered, record.id)
    assert refs == {} and anchors == []


@pytest.mark.asyncio
async def test_find_miss_explicitly_suggests_query_without_an_automatic_retry():
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft())
    result = await _read(
        fixture,
        record.id,
        grants=EvidenceAuthorization(frozenset([record.id])),
        arguments={"find": "a guessed sentence"},
    )
    payload = json.loads(result.preview)
    assert payload["selection"]["reason"] == "find_no_match"
    assert payload["passages"] == []


@pytest.mark.asyncio
async def test_whole_query_group_survives_preview_numbering_with_real_coordinates():
    fixture = build_gateway_fixture()
    body = (
        "If special_flag is false, operations are not cancelled.\n\n"
        "If cleanup fails, errors are aggregated."
    )
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft(body))
    result = await _read(
        fixture,
        record.id,
        grants=EvidenceAuthorization(frozenset([record.id])),
        arguments={"query": "special_flag"},
    )
    numbered, refs, diagnostics = number_read_preview(result.preview, {})
    payload = json.loads(numbered)
    assert not diagnostics
    assert "operations are not cancelled." in numbered
    assert "errors are aggregated." in numbered
    assert refs
    assert all(body[p["start"] : p["end"]] == p["text"] for p in payload["passages"])
