"""An evidence ID alone is not a fact-memory admission credential."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from responses.test_supported_findings import _case
from strategies.fixtures import FIXED_NOW

from deeptrace.domain import MemoryRecord, MemoryType
from deeptrace.harness.memory.lifecycle import _consolidate_memory
from deeptrace.harness.memory.write import MemoryWritePolicy


def test_fact_ids_require_host_verification_not_just_source_labels():
    record = MemoryRecord(
        type=MemoryType.FACT,
        namespace=("workspace", "workspace-1", "facts"),
        subject="fact",
        content="Store fact",
        source_evidence_ids=["e1"],
        confidence=0.9,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    assert MemoryWritePolicy().can_store(record, source="consolidation") is False
    assert (
        MemoryWritePolicy().can_store(
            record, source="consolidation", supported_fact=True
        )
        is True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "unsupported",
        "legacy",
        "wrong_hash",
        "wrong_version",
        "negative_range",
        "wrong_quote",
        "foreign",
        "superseded",
        "deleted",
        "store_outage",
    ],
)
async def test_real_consolidation_only_admits_current_host_verified_support(case):
    from deeptrace.domain import EvidenceLifecycleStatus
    from deeptrace.tools.evidence_store import EvidenceDraft

    payload, _, fixture, _ = await _case()
    finding = payload.research_outcome.findings[0]
    support = finding.supports[0]
    context = fixture.context
    if case == "unsupported":
        finding.supports = []
    elif case == "legacy":
        payload.research_outcome.evidence_contract_version = 1
    elif case in {"wrong_hash", "wrong_version", "negative_range", "wrong_quote"}:
        changes = {
            "wrong_hash": {"content_hash": "wrong"},
            "wrong_version": {"version": 100},
            "negative_range": {"start": -len(support.quote)},
            "wrong_quote": {"quote": "fabricated"},
        }
        finding.supports[0] = support.model_copy(update=changes[case])
    elif case == "foreign":
        context = replace(context, workspace_id="other")
    elif case == "superseded":
        await fixture.evidence_store.ingest(
            "workspace-1",
            EvidenceDraft(
                canonical_url="https://example.com/doc",
                title="Doc",
                body="changed",
                media_type="text/plain",
                fetched_at=FIXED_NOW,
                source_quality=0.9,
            ),
        )
    elif case == "deleted":
        record = await fixture.evidence_store.get("workspace-1", support.evidence_id)
        key = ("workspace-1", record.id)
        fixture.evidence_store._records[key] = replace(
            fixture.evidence_store._records[key],
            evidence=record.model_copy(
                update={"status": EvidenceLifecycleStatus.DELETED}
            ),
        )
        assert (
            await fixture.evidence_store.get(*key)
        ).status is EvidenceLifecycleStatus.DELETED
    elif case == "store_outage":

        class BrokenStore:
            async def get_many(self, *args):
                raise RuntimeError("unavailable")

        context = replace(context, evidence_store=BrokenStore())
    outcome = payload.research_outcome
    assert (
        await _consolidate_memory(
            {"turn": {"research_outcome": outcome}}, SimpleNamespace(context=context)
        )
        == {}
    )
    facts = await fixture.memory_store.list_namespace(
        ("workspace", "workspace-1", "facts")
    )
    if case == "valid":
        assert [f.content for f in facts] == [finding.claim]
        assert facts[0].expires_at == FIXED_NOW + timedelta(days=30)
        await _consolidate_memory(
            {"turn": {"research_outcome": outcome}}, SimpleNamespace(context=context)
        )
        assert (
            await fixture.memory_store.list_namespace(
                ("workspace", "workspace-1", "facts")
            )
            == facts
        )
    else:
        assert facts == []
