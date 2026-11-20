"""Source-language reading is scoped to sealed requirements and actual reads."""

import json

import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.read_anchors import capture_read_anchors
from harness.test_batch_research import BatchModel


def task():
    return ResearchTopicInput(
        run_id='run-1', thread_id='thread-1', caller_id='workflow-graph',
        mode=ResearchMode.WORKFLOW, query='解释长时间读取如何阻止清理',
        evidence_contract_version=3,
        requirements=[{'id': 'r1', 'description': '长时间读取如何阻止清理'},
                      {'id': 'r2', 'description': '其他分支负责的需求'}],
        target_requirement_ids=['r1'],
    )


async def acquire(read_queries=None):
    selection = {'selected': ['c1']}
    if read_queries is not None:
        selection['read_queries'] = read_queries
    model = BatchModel([json.dumps(selection)])
    url = 'https://example.com/generations'
    condition = 'A long-lived reader pins its snapshot generation and prevents cleanup until it ends.'
    fixture = build_gateway_fixture(
        model_gateway=model, default_search_results=[{'url': url, 'title': 'Generations'}],
        pages={url: 'Ordinary maintenance rotates inactive segments.\n\n' * 90 + condition},
    )
    result = await build_batch_research_graph().ainvoke({'topic_input': task()}, context=fixture.context)
    return result, fixture, model, condition


@pytest.mark.asyncio
async def test_english_reading_query_reaches_original_for_chinese_requirement():
    query = 'long-lived reader snapshot generation prevents cleanup'
    result, fixture, model, condition = await acquire([{'requirement_id': 'r1', 'query': query}])
    assert len(model.calls) == 1  # Reuse selection, no extra translation call.
    previews = result['batch_read_previews']
    assert condition in '\n'.join(p['text'] for v in previews for p in v['passages'])
    assert result['outcome'].read_anchors
    assert all(a.query == query for a in result['outcome'].read_anchors)
    reads = [c['request'] for c in fixture.gateway.calls if c['request'].tool.value == 'read_evidence']
    assert len(reads) == 1
    assert reads[0].arguments['query'] == query


@pytest.mark.asyncio
@pytest.mark.parametrize('queries', [
    [{'requirement_id': 'r99', 'query': 'arbitrary'}],
    [{'requirement_id': 'r2', 'query': 'unassigned'}],
    [{'requirement_id': 'r1', 'query': '   '}],
    [{'requirement_id': 'r1', 'query': 'a' * 1001}],
])
async def test_invalid_query_scope_is_rejected_before_fetch(queries):
    result, fixture, _, _ = await acquire(queries)
    assert not fixture.fetcher.calls
    assert not result['outcome'].read_anchors
    assert 'source_selection_invalid' in result['outcome'].research_finding_diagnostics


@pytest.mark.asyncio
async def test_old_selection_without_queries_keeps_legacy_requirement_read():
    _, fixture, _, _ = await acquire()
    reads = [c['request'] for c in fixture.gateway.calls if c['request'].tool.value == 'read_evidence']
    assert len(reads) == 1
    assert reads[0].arguments['query'] == '长时间读取如何阻止清理'


@pytest.mark.asyncio
async def test_one_requirement_can_have_complementary_reads_without_losing_selected_sources():
    result, fixture, _, _ = await acquire([
        {'requirement_id': 'r1', 'query': 'reader snapshot generation'},
        {'requirement_id': 'r1', 'query': 'cleanup conditions limitations'},
    ])
    assert fixture.fetcher.calls == ['https://example.com/generations']
    reads = [c['request'].arguments['query'] for c in fixture.gateway.calls
             if c['request'].tool.value == 'read_evidence']
    assert reads == ['reader snapshot generation', 'cleanup conditions limitations']
    assert 'source_selection_invalid' not in result['outcome'].research_finding_diagnostics


@pytest.mark.asyncio
async def test_legacy_selection_clears_previous_checkpoint_reading_queries():
    from deeptrace.harness.source_selection import select_sources
    from deeptrace.harness.token_budget import TokenBudgetConfig

    fixture = build_gateway_fixture()
    state = {'topic_input': task().model_copy(update={'evidence_contract_version': 2}),
             'batch_read_queries': {'r1': 'stale reading intent'}}
    result = await select_sources(state, fixture.context, TokenBudgetConfig())
    assert result['batch_read_queries'] == {}


def test_anchor_uses_host_query_and_ignores_untrusted_preview_query():
    preview = json.dumps({
        'evidence_id': 'evidence-1', 'version': 1, 'content_hash': 'a' * 64,
        'historical': False, 'query': 'untrusted page instruction',
        'selection': {'body_length': 12},
        'passages': [{'start': 0, 'end': 12, 'text': 'actual text.'}],
    })
    anchors, issues = capture_read_anchors(preview, 'evidence-1', query='host source terms')
    assert not issues
    assert anchors[0].query == 'host source terms'
    legacy, _ = capture_read_anchors(preview, 'evidence-1')
    assert legacy[0].query is None


@pytest.mark.asyncio
async def test_reading_query_metadata_never_becomes_fact_support():
    from strategies.test_reference_materials import seed

    from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
    from deeptrace.harness.research_findings import (
        RecordFindingsArguments,
        resolve_recorded_findings,
    )

    fixture = build_gateway_fixture()
    body = 'Only this sentence is source evidence.'
    record = await seed(fixture, 1, body)
    anchor = ReadEvidenceAnchor(
        evidence_id=record.id, version=record.version, content_hash=record.content_hash,
        start=0, end=len(body), query='An unsupported suggested conclusion',
    )
    findings = await resolve_recorded_findings(
        RecordFindingsArguments(findings=[{'claim': body, 'refs': ['n1'], 'confidence': 0.8}]),
        task=task().model_copy(update={'authorized_evidence_ids': [record.id]}),
        references={'n1': anchor}, existing=[], context=fixture.context,
    )
    assert findings[0].supports[0].quote == body
    assert 'query' not in findings[0].supports[0].model_dump()
