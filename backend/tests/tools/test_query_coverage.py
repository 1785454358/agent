"""An API identifier must not exclude other directly relevant source rules."""
import json
from pathlib import Path

from deeptrace.tools.evidence_views import select_source_excerpt


def frozen_body(identity):
    path = Path(__file__).parents[2] / 'src/deeptrace/evaluation/data/frozen-corpus.json'
    return next(r['body'] for r in json.loads(path.read_text(encoding='utf-8')) if r['id'] == identity)


def test_observed_prerequisite_query_retains_complete_conditions_in_same_window():
    body = frozen_body('langgraph-interrupts')
    excerpt = select_source_excerpt(body,
        'interrupt() prerequisites checkpointer thread_id compile workflow', 3000)
    assert 'payload must be JSON-serializable' in excerpt.text
    assert 'A **thread ID**' in excerpt.text
    assert 'durable checkpointer in production' in excerpt.text
    assert len(excerpt.text) <= 3000
    assert all(body[r.start:r.end] in excerpt.text for r in excerpt.ranges)


def test_api_query_retains_history_validity_warning_alongside_trim_example():
    body = frozen_body('langchain-short-term-memory')
    excerpt = select_source_excerpt(body,
        'trim_messages remove stale messages history pruning rules', 3000)
    assert 'resulting message history is valid' in excerpt.text
    assert 'corresponding `tool` result messages' in excerpt.text
    assert 'trim_messages' in excerpt.text
    assert len(excerpt.text) <= 3000


def test_repeated_identifier_does_not_exclude_multi_term_condition():
    repeated = 'job_id is the identifier supplied to the worker.\n\n'
    rule = 'To pause a job, supply persistent storage and a serializable input value.\n\n'
    body = repeated * 80 + rule + repeated * 80
    excerpt = select_source_excerpt(body, 'job_id pause job storage input', 900)
    assert rule.strip() in excerpt.text
    assert 'job_id' in excerpt.text
    assert len(excerpt.text) <= 900


def test_relevant_warning_keeps_the_rule_and_its_list_as_one_unit():
    repeated = 'job_id identifies the history messages.\n\n'
    warning = ('<Warning>\nWhen deleting history messages, keep the resulting sequence valid.\n\n'
               '* A retained request needs its matching result.\n'
               '* Avoid leaving a result without its request.\n</Warning>\n\n')
    body = repeated * 50 + warning + repeated * 50
    excerpt = select_source_excerpt(body, 'job_id history messages rules', 900)
    assert warning.strip() in excerpt.text
    assert 'job_id' in excerpt.text
    assert len(excerpt.text) <= 900


def test_oversized_callout_is_omitted_without_cutting_its_conditions():
    warning = '<Warning>\nhistory messages rules ' + 'condition ' * 250 + '\n</Warning>\n\n'
    body = 'job_id identifies history messages.\n\n' * 40 + warning
    excerpt = select_source_excerpt(body, 'job_id history messages rules', 600)
    assert 'job_id' in excerpt.text
    assert '<Warning>' not in excerpt.text
    assert 'condition' not in excerpt.text
    assert len(excerpt.text) <= 600


def test_warning_cannot_expand_an_actual_read_scope():
    prefix = 'job_id identifies history messages.\n\n' * 20
    warning = '<Warning>\nhistory messages must remain valid.\n\n* Preserve paired units.\n</Warning>\n\n'
    body = prefix + warning
    excerpt = select_source_excerpt(body, 'job_id history messages rules', 600,
        eligible_ranges=[(0, len(prefix))])
    assert '<Warning>' not in excerpt.text
    assert all(0 <= r.start < r.end <= len(prefix) for r in excerpt.ranges)


def test_unrelated_api_warning_cannot_displace_a_qualified_target_section():
    body = ('## pkg.OpenGroup\n\nA group of concurrent operations.\n\n'
            'When an operation fails, remaining operations are cancelled.\n\n'
            'The errors are grouped after cleanup.\n\n'
            '## pkg.OtherNode\n\n<Warning>\n'
            'Task exception cancellation retry result comparison. '
            + 'Task exception cancellation retry result comparison. ' * 4
            + '\n</Warning>\n\n' + 'Background.\n\n' * 100)
    excerpt = select_source_excerpt(body,
        'pkg.OpenGroup task exception cancellation retry result comparison', 420)
    assert 'remaining operations are cancelled.' in excerpt.text
    assert '<Warning>' not in excerpt.text
