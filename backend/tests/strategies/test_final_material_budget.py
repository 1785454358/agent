"""Global serialization must not let the first source consume all fact slots."""

import pytest

from deeptrace.domain import ResearchRequirement
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.token_budget import TokenBudgetConfig, count_tokens
from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
from deeptrace.tools.evidence_store import EvidenceDraft
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture


@pytest.mark.asyncio
async def test_later_source_condition_survives_global_budget():
    fixture = build_gateway_fixture()
    ids, anchors = [], []
    for index, groups in enumerate(
        [
            ["AlphaGate context note. " * 14] * 3,
            ["BetaGate requires explicit cleanup; do not cancel peers."],
        ]
    ):
        body = "\n\nUNREAD separator.\n\n".join(groups)
        record = await fixture.evidence_store.ingest(
            TENANT_ID,
            EvidenceDraft(
                canonical_url=f"https://example.com/v2/{index}",
                title="Tasks",
                body=body,
                media_type="text/plain",
                fetched_at=FIXED_NOW,
                source_quality=0.9,
            ),
        )
        ids.append(record.id)
        cursor = 0
        for group in groups:
            anchors.append(
                ReadEvidenceAnchor(
                    evidence_id=record.id,
                    version=record.version,
                    content_hash=record.content_hash,
                    start=cursor,
                    end=cursor + len(group),
                )
            )
            cursor += len(group) + len("\n\nUNREAD separator.\n\n")
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="Compare AlphaGate and BetaGate",
        requirements=[
            ResearchRequirement(id="r1", description="AlphaGate context"),
            ResearchRequirement(id="r2", description="BetaGate cleanup"),
        ],
        evidence_ids=ids,
        findings=[],
        read_anchors=anchors,
        budget=TokenBudgetConfig(
            context_tokens=420, output_reserve_tokens=0, safety_tokens=0
        ),
    )
    assert any("do not cancel peers" in p.text for p in view.passages)
    assert any("AlphaGate" in p.text for p in view.passages)
    assert count_tokens(view.prompt) <= 420
    assert "UNREAD" not in view.prompt
