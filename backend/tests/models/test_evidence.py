from datetime import UTC, date, datetime

import pytest

from deeptrace import models


def test_stage_four_evidence_models_validate_lineage_and_serialize() -> None:
    """缺少模型、字段或 exact 位置约束时必须失败。"""
    assert hasattr(models, "Source")
    assert hasattr(models, "Evidence")
    assert hasattr(models, "Claim")

    source = models.Source(
        source_id="source-01",
        doc_id="doc-01",
        requested_url="https://example.com/a",
        final_url="https://example.com/a",
        canonical_url=None,
        title="Agent release",
        publisher="Example Lab",
        source_kind="official",
        publication_date=datetime(2024, 4, 1, tzinfo=UTC),
        modified_date=None,
        fetched_at=datetime(2026, 9, 1, tzinfo=UTC),
        scraper_used="httpx_trafilatura",
        content_hash="content-hash",
    )
    evidence = models.Evidence(
        evidence_id="evidence-01",
        source_id=source.source_id,
        doc_id=source.doc_id,
        note_id="note-01",
        task_id="task-01",
        section_id="section-01",
        quote="The agent was released in 2024.",
        quote_hash="quote-hash",
        char_start=12,
        char_end=43,
        location_status="exact",
        event_start_date=date(2024, 4, 1),
        event_end_date=date(2024, 4, 1),
        temporal_relation="in_range",
    )
    claim = models.Claim(
        claim_id="claim-01",
        task_id="task-01",
        section_id="section-01",
        text="该 Agent 于 2024 年发布。",
        kind="temporal",
        importance="key",
        event_start_date=date(2024, 4, 1),
        event_end_date=date(2024, 4, 1),
        evidence_ids=[evidence.evidence_id],
    )

    assert models.Source.model_validate_json(source.model_dump_json()) == source
    assert models.Evidence.model_validate_json(evidence.model_dump_json()) == evidence
    assert models.Claim.model_validate_json(claim.model_dump_json()) == claim


def test_exact_evidence_requires_character_offsets() -> None:
    assert hasattr(models, "Evidence")

    with pytest.raises(ValueError, match="字符位置"):
        models.Evidence(
            evidence_id="evidence-01",
            source_id="source-01",
            doc_id="doc-01",
            note_id="note-01",
            task_id="task-01",
            section_id="section-01",
            quote="原文",
            quote_hash="hash",
            location_status="exact",
        )
