from datetime import UTC, date, datetime

from deeptrace.models import (
    Claim,
    Evidence,
    NumericDetail,
    ResearchTimeRange,
    Source,
)
from deeptrace.verification import check_claim_rules


RANGE_2024 = ResearchTimeRange(
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
    description="2024",
)


def _source(
    identity: str,
    url: str,
    kind: str = "reputable_secondary",
) -> Source:
    return Source(
        source_id=identity,
        doc_id=f"doc-{identity}",
        requested_url=url,
        final_url=url,
        canonical_url=url,
        title=identity,
        source_kind=kind,
        fetched_at=datetime.now(UTC),
        scraper_used="httpx_trafilatura",
        content_hash=f"hash-{identity}",
    )


def _evidence(
    identity: str,
    source: str,
    *,
    exact: bool = True,
    relation: str = "in_range",
) -> Evidence:
    return Evidence(
        evidence_id=identity,
        source_id=source,
        doc_id=f"doc-{source}",
        note_id=f"note-{identity}",
        task_id="task-01",
        section_id="section-01",
        quote=f"quote-{identity}",
        quote_hash=f"hash-{identity}",
        char_start=0 if exact else None,
        char_end=5 if exact else None,
        location_status="exact" if exact else "unlocated",
        temporal_relation=relation,
    )


def _claim(*evidence_ids: str, numeric=None) -> Claim:
    return Claim(
        claim_id="claim-01",
        task_id="task-01",
        section_id="section-01",
        text="关键主张",
        kind="numeric" if numeric is not None else "factual",
        importance="key",
        numeric=numeric,
        evidence_ids=list(evidence_ids),
    )


def test_missing_and_unlocated_evidence_are_blocking() -> None:
    item = _evidence("ev-unlocated", "source-01", exact=False)
    result = check_claim_rules(
        _claim("ev-unlocated", "ev-missing"),
        {item.evidence_id: item},
        {"source-01": _source("source-01", "https://example.com/a")},
        None,
    )

    assert result.eligible_evidence_ids == []
    assert {issue.code for issue in result.blocking_issues} == {
        "evidence_unlocated",
        "evidence_missing",
    }


def test_out_of_range_claim_is_forced_without_llm() -> None:
    item = _evidence("ev-01", "source-01")
    claim = _claim(item.evidence_id).model_copy(
        update={
            "event_start": date(2025, 1, 1),
            "event_end": date(2025, 1, 1),
        }
    )
    result = check_claim_rules(
        claim,
        {item.evidence_id: item},
        {"source-01": _source("source-01", "https://example.com/a")},
        RANGE_2024,
    )

    assert result.forced_verdict == "out_of_range"
    assert {issue.code for issue in result.blocking_issues} == {
        "claim_out_of_range"
    }


def test_one_weak_source_cannot_support_key_claim() -> None:
    item = _evidence("ev-01", "source-01")
    result = check_claim_rules(
        _claim(item.evidence_id),
        {item.evidence_id: item},
        {
            "source-01": _source(
                "source-01", "https://blog.example/a", "other"
            )
        },
        None,
    )

    assert "source_quality_insufficient" in {
        issue.code for issue in result.blocking_issues
    }


def test_two_subdomains_are_one_source_identity() -> None:
    first = _evidence("ev-01", "source-01")
    second = _evidence("ev-02", "source-02")
    result = check_claim_rules(
        _claim(first.evidence_id, second.evidence_id),
        {first.evidence_id: first, second.evidence_id: second},
        {
            "source-01": _source(
                "source-01", "https://news.example.com/a"
            ),
            "source-02": _source(
                "source-02", "https://research.example.com/b"
            ),
        },
        None,
    )

    assert result.source_identities == ["example.com"]
    assert "source_independence_insufficient" in {
        issue.code for issue in result.blocking_issues
    }


def test_two_independent_qualified_sources_pass_local_gates() -> None:
    first = _evidence("ev-01", "source-01")
    second = _evidence("ev-02", "source-02")
    result = check_claim_rules(
        _claim(first.evidence_id, second.evidence_id),
        {first.evidence_id: first, second.evidence_id: second},
        {
            "source-01": _source(
                "source-01", "https://example.com/a"
            ),
            "source-02": _source(
                "source-02", "https://another.org/b"
            ),
        },
        None,
    )

    assert result.blocking_issues == []
    assert result.forced_verdict is None


def test_one_authoritative_direct_source_can_reach_semantic_verification() -> None:
    item = _evidence("ev-01", "source-01")
    result = check_claim_rules(
        _claim(item.evidence_id),
        {item.evidence_id: item},
        {
            "source-01": _source(
                "source-01", "https://lab.example/release", "official"
            )
        },
        None,
    )

    assert result.blocking_issues == []
    assert result.forced_verdict is None


def test_numeric_claim_requires_unit_scope_and_time_basis() -> None:
    item = _evidence("ev-01", "source-01")
    claim = _claim(
        item.evidence_id,
        numeric=NumericDetail(value_text="42"),
    )
    result = check_claim_rules(
        claim,
        {item.evidence_id: item},
        {
            "source-01": _source(
                "source-01", "https://lab.example/data", "official"
            )
        },
        RANGE_2024,
    )

    assert {issue.code for issue in result.blocking_issues} == {
        "numeric_unit_missing",
        "numeric_scope_missing",
        "numeric_time_basis_missing",
    }

