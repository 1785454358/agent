"""Choosing evidence is model work; constructing raw quotes is host work."""

from deeptrace.tools.evidence_views import EvidencePassage


def passage():
    return EvidencePassage(
        "source", 1, "hash", "internal-long-id", 7, 28, 1, 2, "`key`\nnot optional. 🧭"
    )


def test_ref_generates_exact_raw_support_without_copying_metadata():
    from deeptrace.strategies.evidence_references import (
        ReferenceFindingDraft,
        normalize_reference_findings,
    )

    draft = ReferenceFindingDraft(
        id="f1", claim="The key is required.", confidence=0.8, supports=[{"ref": "p1"}]
    )
    findings, diagnostics = normalize_reference_findings([draft], {"p1": passage()})
    support = findings[0].supports[0]
    assert (support.start, support.end, support.quote) == (
        7,
        28,
        "`key`\nnot optional. 🧭",
    )
    assert findings[0].evidence_ids == ["source"]
    assert not diagnostics


def test_unknown_ref_cannot_create_coverage_material():
    from deeptrace.strategies.evidence_references import (
        ReferenceFindingDraft,
        normalize_reference_findings,
    )

    draft = ReferenceFindingDraft(
        id="f1", claim="claim", confidence=0.8, supports=[{"ref": "p2"}]
    )
    findings, diagnostics = normalize_reference_findings([draft], {"p1": passage()})
    assert findings == []
    assert "invalid_support_reference" in diagnostics


def test_duplicate_finding_ids_are_rejected_not_merged():
    from deeptrace.strategies.evidence_references import (
        ReferenceFindingDraft,
        normalize_reference_findings,
    )

    draft = ReferenceFindingDraft(
        id="f1", claim="claim", confidence=0.8, supports=[{"ref": "p1"}]
    )
    findings, diagnostics = normalize_reference_findings(
        [draft, draft], {"p1": passage()}
    )
    assert findings == []
    assert diagnostics == ["duplicate_finding_id"]
