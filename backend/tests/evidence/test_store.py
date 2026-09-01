from datetime import UTC, datetime

from deeptrace.evidence import EvidenceStore
from deeptrace.models import Claim, Evidence, Source


def _source(source_id: str, doc_id: str) -> Source:
    return Source(
        source_id=source_id,
        doc_id=doc_id,
        requested_url=f"https://{doc_id}.example/a",
        final_url=f"https://{doc_id}.example/a",
        canonical_url=None,
        title=doc_id,
        publisher=None,
        source_kind="official",
        fetched_at=datetime.now(UTC),
        scraper_used="httpx_trafilatura",
        content_hash=f"hash-{doc_id}",
    )


def _evidence(evidence_id: str, source_id: str, note_id: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_id=source_id,
        doc_id=source_id.replace("source", "doc"),
        note_id=note_id,
        task_id="task-01",
        section_id="section-01",
        quote=f"quote-{evidence_id}",
        quote_hash=f"hash-{evidence_id}",
        location_status="unlocated",
    )


def test_claim_reverse_lookup_preserves_first_use_order() -> None:
    first = _evidence("evidence-01", "source-01", "note-01")
    second = _evidence("evidence-02", "source-02", "note-02")
    duplicate_source = _evidence("evidence-03", "source-01", "note-03")
    claim = Claim(
        claim_id="claim-01",
        task_id="task-01",
        section_id="section-01",
        text="一个主张",
        kind="factual",
        importance="key",
        evidence_ids=[
            second.evidence_id,
            first.evidence_id,
            duplicate_source.evidence_id,
        ],
    )
    store = EvidenceStore(
        sources={
            "source-01": _source("source-01", "doc-01"),
            "source-02": _source("source-02", "doc-02"),
        },
        evidence={
            first.evidence_id: first,
            second.evidence_id: second,
            duplicate_source.evidence_id: duplicate_source,
        },
        claims={claim.claim_id: claim},
    )

    assert [item.evidence_id for item in store.evidence_for_claim(claim.claim_id)] == [
        "evidence-02",
        "evidence-01",
        "evidence-03",
    ]
    assert [item.source_id for item in store.sources_for_claim(claim.claim_id)] == [
        "source-02",
        "source-01",
    ]


def test_upsert_returns_new_store_without_mutating_original() -> None:
    original = EvidenceStore()
    updated = original.upsert_sources([_source("source-01", "doc-01")])

    assert original.sources == {}
    assert set(updated.sources) == {"source-01"}
    assert updated.sources is not original.sources

