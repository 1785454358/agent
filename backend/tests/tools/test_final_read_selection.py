"""Late read conditions must survive evaluation without borrowing unread text."""

import pytest
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture

from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.tools.evidence_store import EvidenceDraft
from deeptrace.tools.evidence_units import select_read_passages


@pytest.mark.asyncio
async def test_large_generic_read_cannot_displace_late_api_conditions():
    early = ("BatchAwait CancelFlag generic task notes and examples. " * 80)[:3000]
    unseen = "\n\nUNREAD: secret condition.\n\n" * 40
    fact = "# BatchAwait\n\nIf include_errors=True, failures become results. Otherwise propagate the first error without cancelling peers.\n\n"
    body = early + unseen + fact
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/v2/tasks",
            title="Tasks",
            body=body,
            media_type="text/plain",
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )
    anchors = [
        ReadEvidenceAnchor(
            evidence_id=record.id,
            version=record.version,
            content_hash=record.content_hash,
            start=a,
            end=b,
        )
        for a, b in [(0, 1000), (1000, 3000), (len(body) - len(fact), len(body))]
    ]
    passages, issues = select_read_passages(
        record,
        body,
        [],
        anchors,
        question="Compare BatchAwait and CancelFlag.",
        focus_queries=["BatchAwait error handling", "CancelFlag cleanup"],
        limit=3000,
    )
    text = "\n".join(p.text for p in passages)
    assert "include_errors=True" in text
    assert "without cancelling peers" in text
    assert "UNREAD" not in text
    assert sum(len(p.text) for p in passages) <= 3000
    assert all(p.text == body[p.start : p.end] for p in passages)
    assert all(p.end <= 3000 or p.start >= len(body) - len(fact) for p in passages)
    assert "read_anchor_omitted" in issues


def test_restricted_selection_never_borrows_unread_heading_or_conditions():
    from deeptrace.tools.evidence_views import select_source_excerpt

    body = "# BatchAwait\n\nUNREAD failure.\n\nvisible cleanup.\n\n" + "junk\n\n" * 500
    start = body.index("visible")
    end = start + len("visible cleanup.\n\n")
    excerpt = select_source_excerpt(
        body, "BatchAwait", 300, eligible_ranges=[(start, end)]
    )
    assert "visible cleanup." in excerpt.text
    assert "UNREAD" not in excerpt.text
    assert "# BatchAwait" not in excerpt.text
    assert [(p.start, p.end) for p in excerpt.ranges] == [(start, end)]


@pytest.mark.parametrize("ranges", [[(-1, 2)], [(0, 99999)], [(True, 3)]])
def test_restricted_selection_rejects_invalid_coordinates(ranges):
    from deeptrace.tools.evidence_views import select_source_excerpt

    with pytest.raises(ValueError, match="invalid.*range"):
        select_source_excerpt("body", "body", 100, eligible_ranges=ranges)
