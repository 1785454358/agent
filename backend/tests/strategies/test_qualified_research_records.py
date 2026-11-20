"""Keep qualified experimental facts instead of reinterpreting naked scores."""

from datetime import date

from deeptrace.strategies.evidence_references import ReferenceFindingDraft, normalize_reference_findings
from deeptrace.tools.evidence_views import EvidencePassage


def passage(text, source="paper-a", start=0):
    return EvidencePassage(source, 1, "sha256:" + "a" * 64, "span", start,
        start + len(text), 1, 1, text)


def resolve(experiments=None):
    refs = {
        "p1": passage("Published: 22 January 2025. Original experimental report."),
        "p2": passage("Model-R1 | MATH-500 | accuracy | 97.3", start=100),
        "p3": passage("Maximum generation length is 32,768 tokens. Temperature 0.6.", start=200),
        "p4": passage("Model-Zero | accuracy | 95.9", source="paper-b"),
    }
    data = {"id": "f1", "claim": "Results depend on the evaluation protocol.",
        "confidence": 0.9, "supports": [{"ref": "p2"}],
        "research_result": {"kind": "original_experiment", "title": "A reasoning study",
            "published_on": "2025-01-22", "date_refs": ["p1"]}}
    if experiments is not None:
        data["experiments"] = experiments
    return normalize_reference_findings([ReferenceFindingDraft.model_validate(data)], refs,
        source_policy="research_results", publication_years=[2025], cutoff=date(2026, 11, 17))


def experiment():
    return {"model": {"value": "Model-R1", "refs": ["p2"]},
        "dataset": {"value": "MATH-500", "refs": ["p2"]},
        "metric": {"value": "accuracy", "refs": ["p2"]},
        "result": {"value": "97.3", "refs": ["p2"]},
        "budget": {"value": "32,768 tokens", "refs": ["p3"]},
        "conditions": {"value": "Temperature 0.6", "refs": ["p3"]}}


def test_normalization_keeps_research_identity_instead_of_discarding_it():
    findings, issues = resolve()
    assert not issues
    assert findings[0].research_result.title == "A reasoning study"
    assert findings[0].research_result.published_on == date(2025, 1, 22)


def test_protocol_and_score_remain_bound_to_their_own_original_supports():
    findings, issues = resolve([experiment()])
    assert not issues
    finding = findings[0]
    record = finding.experiments[0]
    assert record.model.value == "Model-R1"
    assert record.result.value == "97.3"
    assert record.budget.value == "32,768 tokens"
    assert "Temperature 0.6" in finding.supports[record.conditions.support_indices[0]].quote
    assert all(finding.supports[i].evidence_id == "paper-a"
        for i in record.result.support_indices)


def test_foreign_paper_score_is_rejected_without_erasing_other_fields():
    draft = experiment()
    draft["result"] = {"value": "95.9", "refs": ["p4"]}
    findings, issues = resolve([draft])
    assert findings[0].experiments[0].result is None
    assert findings[0].experiments[0].model.value == "Model-R1"
    assert any("result" in issue for issue in issues)
    assert all(s.evidence_id == "paper-a" for s in findings[0].supports)


def test_invented_value_and_unknown_ref_do_not_erase_valid_protocol():
    draft = experiment()
    draft["result"]["value"] = "99.9"
    draft["dataset"]["refs"] = ["p99"]
    findings, issues = resolve([draft])
    assert findings[0].experiments[0].result is None
    assert findings[0].experiments[0].dataset is None
    assert findings[0].experiments[0].budget.value == "32,768 tokens"
    assert len(issues) == 2


def test_malformed_optional_cell_does_not_invalidate_entire_assessment():
    draft = experiment()
    draft["result"] = "97.3"  # common provider placement error, no actual refs
    findings, issues = resolve([draft])
    assert findings[0].experiments[0].result is None
    assert findings[0].experiments[0].budget.value == "32,768 tokens"
    assert any("result" in issue for issue in issues)


def test_accuracy_metric_cannot_be_saved_as_compute_budget():
    draft = experiment()
    draft["budget"] = {"value": "accuracy", "refs": ["p2"]}
    findings, issues = resolve([draft])
    assert findings[0].experiments[0].budget is None
    assert findings[0].experiments[0].metric.value == "accuracy"
    assert any("budget" in issue for issue in issues)
