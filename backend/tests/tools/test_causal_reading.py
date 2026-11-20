"""A short causal conclusion must retain the preceding condition it relies on."""

import pytest

from deeptrace.tools.evidence_views import select_source_excerpt

CONDITION = (
    'Compaction can copy old generations while clients are active. '
    'It stops only at a generation that a current reader still needs. '
    'Earlier generations can already be collected.\n\n'
)
CONCLUSION = 'Thus a long-lived reader can delay compaction progress.\n\n'
NOISE = 'A reader requests compaction statistics from the manager.\n\n'


@pytest.mark.parametrize('limit', [300, 450, 600])
def test_causal_conclusion_keeps_its_whole_preceding_condition(limit):
    body = NOISE * 60 + CONDITION + CONCLUSION + NOISE * 20
    excerpt = select_source_excerpt(body, 'long-lived reader compaction progress', limit)
    assert CONDITION + CONCLUSION in '\n'.join(body[r.start:r.end] for r in excerpt.ranges)
    assert len(excerpt.text) <= limit
    assert all(body[r.start:r.end] in excerpt.text for r in excerpt.ranges)


def test_tight_budget_omits_the_group_instead_of_publishing_only_its_conclusion():
    body = NOISE * 60 + CONDITION + CONCLUSION
    excerpt = select_source_excerpt(body, 'long-lived reader compaction progress', 150)
    assert CONCLUSION.strip() not in excerpt.text
    assert len(excerpt.text) <= 150


def test_context_grouping_does_not_cross_a_gap_in_actual_read_ranges():
    body = CONDITION + CONCLUSION + NOISE * 30
    start = len(CONDITION)
    excerpt = select_source_excerpt(
        body, 'long-lived reader compaction progress', 150,
        eligible_ranges=[(start, start + len(CONCLUSION))],
    )
    assert all(r.start >= start for r in excerpt.ranges)


def test_independent_focus_keeps_multiple_target_terms_over_a_short_generic_match():
    generic = 'WORKER_BUSY read transaction checkpoint statistics are available.\n\n'
    condition = (
        'A reader keeps its snapshot generation stable while other sessions continue. ' * 7
        + 'A checkpoint must stop when reaching a version still in use by a current reader.\n\n'
    )
    conclusion = 'Thus a long-running read transaction can prevent checkpoint progress until its snapshot is released.\n\n'
    body = (generic * 5 + 'Plain arithmetic operators are documented separately.\n\n' * 90
            + condition + conclusion)
    excerpt = select_source_excerpt(
        body, '比较 WORKER_BUSY 和长读事务', 1400,
        focus_queries=['WORKER_BUSY writer lock',
                       'long-running read transaction checkpoint progress snapshot',
                       'checkpoint automatic manual interval'],
    )
    assert condition + conclusion in '\n'.join(body[r.start:r.end] for r in excerpt.ranges)
    assert 'WORKER_BUSY' in excerpt.text
    assert len(excerpt.text) <= 1400
