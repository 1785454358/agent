from deeptrace.evidence import claim_id, evidence_id, source_id


def test_stable_ids_are_repeatable_and_namespaced() -> None:
    assert source_id("doc-01") == source_id("doc-01")
    assert source_id("doc-01").startswith("source-")
    assert evidence_id("source-01", "note-01", "hash", 3).startswith(
        "evidence-"
    )
    assert claim_id("task-01", "section-01", "同一主张") == claim_id(
        "task-01", "section-01", "同一主张"
    )


def test_stable_ids_change_when_identity_input_changes() -> None:
    assert source_id("doc-01") != source_id("doc-02")
    assert evidence_id("source-01", "note-01", "hash", 3) != evidence_id(
        "source-01", "note-01", "hash", 4
    )

