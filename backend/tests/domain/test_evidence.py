from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deeptrace.domain.evidence import (
    MAX_EVIDENCE_METADATA_BYTES,
    Evidence,
    EvidenceLifecycleStatus,
    Finding,
)


def _evidence_payload() -> dict[str, object]:
    return {
        "id": "evidence-1",
        "canonical_url": "https://example.com/research",
        "title": "Research source",
        "media_type": "text/html",
        "content_hash": "sha256:" + "a" * 64,
        "fetched_at": datetime(2026, 9, 10, 8, 0, tzinfo=UTC),
        "published_at": datetime(2026, 9, 9, 8, 0, tzinfo=UTC),
        "source_quality": 0.9,
        "status": EvidenceLifecycleStatus.ACTIVE,
        "version": 2,
        "supersedes": "evidence-0",
        "metadata": {"language": "zh-CN", "authors": ["Researcher"]},
    }


def test_evidence_lifecycle_contains_the_defined_states() -> None:
    assert {member.value for member in EvidenceLifecycleStatus} == {
        "candidate",
        "active",
        "stale",
        "superseded",
        "expired",
        "deleted",
    }


def test_evidence_reference_records_provenance_and_version_lifecycle() -> None:
    evidence = Evidence.model_validate(_evidence_payload())

    assert evidence.status is EvidenceLifecycleStatus.ACTIVE
    assert evidence.version == 2
    assert evidence.supersedes == "evidence-0"
    assert evidence.published_at is not None
    assert "content" not in Evidence.model_fields
    assert "body" not in Evidence.model_fields


def test_evidence_reference_does_not_accept_full_content() -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(
            {
                **_evidence_payload(),
                "body": "full page content belongs in the Evidence Store",
            }
        )


@pytest.mark.parametrize(
    "field_name",
    ["canonical_url", "title", "media_type", "content_hash"],
)
def test_evidence_rejects_whitespace_only_provenance_fields(
    field_name: str,
) -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate({**_evidence_payload(), field_name: " \t "})


def test_evidence_validates_quality_version_timestamps_and_supersedes() -> None:
    for update in (
        {"source_quality": 1.1},
        {"version": 0},
        {"fetched_at": datetime(2026, 9, 10, 8, 0)},
        {"supersedes": "evidence-1"},
    ):
        with pytest.raises(ValidationError):
            Evidence.model_validate({**_evidence_payload(), **update})


def test_evidence_metadata_is_json_compatible_and_bounded() -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(
            {**_evidence_payload(), "metadata": {"client": object()}}
        )

    with pytest.raises(ValidationError, match="metadata exceed"):
        Evidence.model_validate(
            {
                **_evidence_payload(),
                "metadata": {"value": "x" * MAX_EVIDENCE_METADATA_BYTES},
            }
        )


def test_existing_finding_contract_remains_available() -> None:
    finding = Finding(
        id="finding-1",
        claim="Evidence remains separate from findings",
        evidence_ids=["evidence-1"],
        confidence=0.8,
    )

    assert finding.evidence_ids == ["evidence-1"]
