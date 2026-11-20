"""Verified reading intent survives bounded parent material selection."""

import pytest

from deeptrace.domain import ResearchRequirement
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor, merge_read_anchors
from deeptrace.harness.token_budget import TokenBudgetConfig, count_tokens
from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
async def test_english_condition_survives_chinese_parent_query_under_same_cap():
    fixture = build_gateway_fixture()
    condition = 'A long-lived reader pins its snapshot generation and prevents cleanup until it ends.'
    body = ('Engine maintenance is ordinary background work.\n\n' * 110 + condition)
    record = await seed(fixture, 1, body)
    anchor = ReadEvidenceAnchor(
        evidence_id=record.id, version=record.version, content_hash=record.content_hash,
        start=0, end=len(body), query='long-lived reader snapshot generation cleanup',
    )
    view = await assemble_reference_evaluation_view(
        fixture.context, question='长时间读取如何阻止清理',
        requirements=[ResearchRequirement(id='r1', description='长时间读取如何阻止清理')],
        evidence_ids=[record.id], findings=[], read_anchors=[anchor],
        budget=TokenBudgetConfig(context_tokens=2500, output_reserve_tokens=0, safety_tokens=0),
    )
    assert condition in '\n'.join(p.text for p in view.passages)
    assert sum(len(p.text) for p in view.passages) <= 3000
    assert view.allocation.used_tokens == count_tokens(view.prompt) <= 2500
    assert all(p.text == body[p.start:p.end] for p in view.passages)


def test_same_range_retains_distinct_reading_intents_with_existing_cap():
    base = {'evidence_id': 'evidence-1', 'version': 1, 'content_hash': 'a' * 64, 'start': 0, 'end': 20}
    a = ReadEvidenceAnchor(**base, query='first intent')
    b = ReadEvidenceAnchor(**base, query='second intent')
    merged = merge_read_anchors([a], [b, a])
    assert len(merged) == 1
    assert merged[0].queries == ('first intent', 'second intent')


def test_duplicate_reading_intents_cannot_displace_a_later_distinct_range():
    base = {'evidence_id': 'evidence-1', 'version': 1, 'content_hash': 'a' * 64, 'start': 0, 'end': 20}
    duplicates = [ReadEvidenceAnchor(**base, query=f'intent {i}') for i in range(64)]
    late = ReadEvidenceAnchor(**{**base, 'start': 30, 'end': 50}, query='later requirement')
    merged = merge_read_anchors([], [*duplicates, late])
    assert len(merged) == 2
    assert merged[-1].start == 30
    assert len(merged[0].queries) <= 6


def test_old_checkpoint_query_field_is_migrated_to_bounded_query_metadata():
    anchor = ReadEvidenceAnchor.model_validate({
        'evidence_id': 'evidence-1', 'version': 1, 'content_hash': 'a' * 64,
        'start': 0, 'end': 20, 'query': 'old checkpoint intent',
    })
    assert anchor.queries == ('old checkpoint intent',)
    assert anchor.query == 'old checkpoint intent'
