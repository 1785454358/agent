"""Citation metadata must not displace a complete raw conditional passage."""

import json
from dataclasses import asdict

import pytest
from harness.test_record_findings_loop import seed
from strategies.fixtures import build_gateway_fixture

from deeptrace.harness.read_anchors import capture_read_anchors
from deeptrace.harness.research_findings import number_read_preview
from deeptrace.tools.evidence_views import (
    make_evidence_passage,
    select_evidence_passages,
)


@pytest.mark.asyncio
async def test_numbered_preview_retains_tail_condition_and_valid_read_anchors():
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    body = (
        "gather documentation. "
        + "supporting detail. " * 130
        + "Other awaitables will not be cancelled."
    )
    preview = json.dumps(
        {
            "evidence_id": record.id,
            "version": record.version,
            "content_hash": record.content_hash,
            "historical": False,
            "selection": {"body_length": len(body), "omitted": False},
            "passages": [asdict(make_evidence_passage(record, body, 0, len(body)))],
        }
    )
    rendered, refs, diagnostics = number_read_preview(preview, {})
    payload = json.loads(rendered)
    assert len(rendered) <= 4000
    assert "".join(p["text"] for p in payload["passages"]) == body
    assert "Other awaitables will not be cancelled." in rendered
    assert not payload["selection"]["omitted"]
    anchors, issues = capture_read_anchors(rendered, record.id)
    assert not issues and not diagnostics
    assert anchors and set(refs) == {p["ref"] for p in payload["passages"]}
    assert all(body[a.start : a.end] for a in anchors)


@pytest.mark.asyncio
async def test_multiline_inline_nodes_do_not_split_a_conditional_sentence():
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    prefix = "gather\n" + "inline\n" * 125
    conditional = (
        "If\nreturn_exceptions\nis\nFalse, other awaitables\nwill not be cancelled.\n"
    )
    body = prefix + conditional + "\n\n" + "unrelated.\n" * 500
    passages = select_evidence_passages(
        record, body, query="return_exceptions", start=None, limit=1800
    )
    assert any(conditional in p.text for p in passages)
    assert all(body[p.start : p.end] == p.text for p in passages)


@pytest.mark.asyncio
async def test_numbering_omits_whole_oversized_reading_group():
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    body = "If the flag is false, " + '\\"' * 1100 + " other tasks are not cancelled."
    preview = json.dumps(
        {
            "evidence_id": record.id,
            "version": record.version,
            "content_hash": record.content_hash,
            "historical": False,
            "selection": {"body_length": len(body), "omitted": False},
            "passages": [asdict(make_evidence_passage(record, body, 0, len(body)))],
        }
    )
    rendered, refs, diagnostics = number_read_preview(preview, {})
    assert json.loads(rendered)["passages"] == []
    assert refs == {} and "read_reference_omitted" in diagnostics


@pytest.mark.asyncio
async def test_read_anchor_budget_does_not_keep_only_half_a_condition():
    from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
    from deeptrace.tools.evidence_units import select_read_passages

    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    body = (
        "If special_flag is false, "
        + "explanation " * 60
        + " other tasks are not cancelled."
    )
    anchors = [
        ReadEvidenceAnchor(
            evidence_id=record.id,
            version=record.version,
            content_hash=record.content_hash,
            start=a,
            end=b,
        )
        for a, b in [(0, 500), (500, len(body))]
    ]
    passages, _ = select_read_passages(
        record, body, [], anchors, question="special_flag", focus_queries=[], limit=500
    )
    assert not any("If special_flag is false" in p.text for p in passages)
