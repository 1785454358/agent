"""Evaluator must see primary text, not a researcher's confident guess."""

import json

import pytest

from deeptrace.domain import EvidenceSupport, Finding, ResearchRequirement
from deeptrace.harness.token_budget import TokenBudgetConfig
from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
async def test_candidate_claim_and_priority_cannot_bias_primary_evidence_view():
    fixture = build_gateway_fixture()
    body = (
        "gather runs awaitables. "
        + "Details. " * 70
        + "Other awaitables are not cancelled."
    )
    record = await seed(fixture, 1, body)
    note = Finding(
        id="candidate",
        claim="FALSE_CANDIDATE cancels others",
        confidence=1,
        evidence_ids=[record.id],
        supports=[
            EvidenceSupport(
                evidence_id=record.id,
                version=1,
                content_hash=record.content_hash,
                start=0,
                end=22,
                quote=body[:22],
            )
        ],
    )
    kwargs = {
        "question": "gather awaitables cancelled",
        "requirements": [
            ResearchRequirement(id="r1", description="other awaitables cancellation")
        ],
        "evidence_ids": [record.id],
        "findings": [],
        "read_anchors": [],
    }
    view = await assemble_reference_evaluation_view(
        fixture.context, research_findings=[note], **kwargs
    )
    clean = await assemble_reference_evaluation_view(fixture.context, **kwargs)
    assert view.prompt == clean.prompt
    assert "FALSE_CANDIDATE" not in view.prompt
    assert "Other awaitables are not cancelled." in view.prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens", [120, 160, 190, 220, 250, 400, 2000])
async def test_budget_keeps_whole_reading_group_or_omits_it(tokens):
    fixture = build_gateway_fixture()
    body = "gather " + "explanation " * 75 + "does not cancel the other awaitables."
    record = await seed(fixture, 1, body)
    view = await assemble_reference_evaluation_view(
        fixture.context,
        question="gather",
        requirements=[],
        evidence_ids=[record.id],
        findings=[],
        read_anchors=[],
        budget=TokenBudgetConfig(
            context_tokens=tokens, output_reserve_tokens=0, safety_tokens=0
        ),
    )
    payload = json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:\n", 1)[1])
    text = "".join(p["text"] for p in payload["passages"])
    assert text in ("", body)
    if tokens == 2000:
        assert text == body
    assert all(
        len(p.text) <= 500 and body[p.start : p.end] == p.text
        for p in view.references.values()
    )
