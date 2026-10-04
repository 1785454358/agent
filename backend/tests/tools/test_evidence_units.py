"""Source material stays verbatim, bounded and read-first, not gold-aware."""

from itertools import pairwise

import pytest
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture

from deeptrace.domain import EvidenceSupport
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.tools.evidence_store import EvidenceDraft
from deeptrace.tools.evidence_views import make_evidence_passage


async def source(body):
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/units",
            title="Units",
            media_type="text/plain",
            body=body,
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )
    return record


@pytest.mark.asyncio
async def test_read_range_survives_broad_query_and_slice_budget():
    from deeptrace.tools.evidence_units import select_read_passages

    fact = "`key`\nnot optional. 🧭"
    body = "Alpha aperture voltage.\n\n" * 200 + fact
    record = await source(body)
    anchor = ReadEvidenceAnchor(
        evidence_id=record.id,
        version=1,
        content_hash=record.content_hash,
        start=len(body) - 21,
        end=len(body),
    )
    passages, diagnostics = select_read_passages(
        record,
        body,
        [],
        [anchor],
        question="Alpha aperture voltage",
        focus_queries=[],
        limit=50,
    )
    assert any(fact in p.text for p in passages)
    assert sum(len(p.text) for p in passages) <= 50
    assert all(p.text == body[p.start : p.end] for p in passages)
    assert not diagnostics


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["z" * 1203, "句子。\n" * 250, "one. two!\n" * 100])
async def test_quote_units_partition_raw_ranges_without_gaps_or_rewrite(text):
    from deeptrace.tools.evidence_units import split_quote_units

    record = await source("prefix:" + text)
    passage = make_evidence_passage(record, "prefix:" + text, 7, 7 + len(text))
    units = split_quote_units((passage,), [])
    assert len(units) > 1
    assert all(1 <= len(p.text) <= 500 for p in units)
    assert "".join(p.text for p in units) == text
    assert units[0].start == 7
    assert units[-1].end == 7 + len(text)
    assert all(a.end == b.start for a, b in pairwise(units))


@pytest.mark.asyncio
async def test_accepted_quote_is_not_split_by_surrounding_material():
    from deeptrace.tools.evidence_units import split_quote_units

    body = "a" * 300 + "b" * 480 + "c" * 200
    record = await source(body)
    support = EvidenceSupport(
        evidence_id=record.id,
        version=1,
        content_hash=record.content_hash,
        start=300,
        end=780,
        quote="b" * 480,
    )
    units = split_quote_units(
        (make_evidence_passage(record, body, 0, len(body)),), [support]
    )
    assert any(p.start == 300 and p.end == 780 and p.text == "b" * 480 for p in units)
    ordered = sorted(units, key=lambda p: p.start)
    assert "".join(p.text for p in ordered) == body


@pytest.mark.asyncio
async def test_stale_anchor_cannot_displace_current_fallback_material():
    from deeptrace.tools.evidence_units import select_read_passages

    body = "Alpha voltage.\n\n" * 200 + "Secret unsupported tail."
    record = await source(body)
    anchor = ReadEvidenceAnchor(
        evidence_id=record.id,
        version=9,
        content_hash=record.content_hash,
        start=len(body) - 24,
        end=len(body),
    )
    passages, diagnostics = select_read_passages(
        record,
        body,
        [],
        [anchor],
        question="Alpha voltage",
        focus_queries=[],
        limit=300,
    )
    assert all("Secret unsupported tail" not in p.text for p in passages)
    assert "invalid_read_anchor" in diagnostics


@pytest.mark.asyncio
async def test_late_relevant_read_displaces_early_unrelated_read():
    from deeptrace.tools.evidence_units import select_read_passages

    body = "unrelated preface. " * 100 + "Context key required."
    record = await source(body)
    anchors = [
        ReadEvidenceAnchor(
            evidence_id=record.id,
            version=record.version,
            content_hash=record.content_hash,
            start=a,
            end=b,
        )
        for a, b in [(0, 1000), (len(body) - 21, len(body))]
    ]
    passages, _ = select_read_passages(
        record,
        body,
        [],
        anchors,
        question="Context key",
        focus_queries=["Context key required"],
        limit=50,
    )
    assert any("Context key required." in p.text for p in passages)
