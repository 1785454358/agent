"""A whole scholarly read must survive the acquisition/evaluation boundary."""

import pytest
from deeptrace.domain import ResearchRequirement
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.token_budget import TokenBudgetConfig
from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
async def test_scientific_evaluator_keeps_opening_and_read_experimental_setup_when_budget_allows():
    fixture = build_gateway_fixture()
    opening = 'Published: 6 August 2024.\nAbstract: inference compute scaling.\n' + 'Opening context. ' * 100
    setup = '## Experimental setup\nMODEL_X uses MATH with 128 samples.\n' + 'Evaluation protocol. ' * 100
    body = opening + '\n\n' + 'Unrelated background. ' * 300 + '\n\n' + setup
    record = await seed(fixture, 1, body)
    anchors = [ReadEvidenceAnchor(evidence_id=record.id, version=record.version, content_hash=record.content_hash,
        start=first, end=last) for first, last in [(0, len(opening)), (body.index(setup), len(body))]]
    view = await assemble_reference_evaluation_view(fixture.context,
        question='Compare original studies and experimental settings',
        requirements=[ResearchRequirement(id='r1', description='Model, benchmark, compute budget and result')],
        evidence_ids=[record.id], findings=[], read_anchors=anchors, prefer_research_passages=True,
        budget=TokenBudgetConfig(context_tokens=15000, output_reserve_tokens=0, safety_tokens=0))
    text = ''.join(p.text for p in view.passages)
    assert opening in text
    assert setup in text
    assert 'read_anchor_omitted:' + record.id not in view.diagnostics
    assert view.allocation.used_tokens <= 15000
