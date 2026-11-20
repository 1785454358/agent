"""A recovery branch can follow a real source link when search has no result."""

import pytest

from harness.test_batch_research import BatchModel, run
from responses.test_graph import _seed_evidence
from strategies.fixtures import build_gateway_fixture
from deeptrace.tools.evidence_store import InMemoryEvidenceStore


@pytest.mark.asyncio
async def test_source_link_is_acquired_through_normal_page_and_read_boundaries():
    store = InMemoryEvidenceStore()
    identities = await _seed_evidence(store, [('https://example.com/overview', 'Overview',
        'For topic pricing see https://example.com/pricing .\nUnrelated https://example.com/jobs .')])
    fixture = build_gateway_fixture(model_gateway=BatchModel(), evidence_store=store,
        default_search_results=[], pages={'https://example.com/pricing':'topic price is 40 per person.'})
    result = await run(fixture, authorized_evidence_ids=identities)
    assert fixture.fetcher.calls == ['https://example.com/pricing']
    assert result['outcome'].evidence_ids
    assert result['outcome'].read_anchors


@pytest.mark.asyncio
async def test_navigation_does_not_invent_links_or_read_ungranted_parent_sources():
    store = InMemoryEvidenceStore()
    await _seed_evidence(store, [('https://example.com/overview', 'Overview',
        'topic https://example.com/private-parent-link .')])
    fixture = build_gateway_fixture(model_gateway=BatchModel(), evidence_store=store, default_search_results=[])
    result = await run(fixture)
    assert not fixture.fetcher.calls
    assert not result['outcome'].evidence_ids


@pytest.mark.asyncio
async def test_navigation_respects_frozen_corpus_and_public_url_boundary():
    from dataclasses import replace
    from deeptrace.domain import ResearchTopicInput, ResearchMode
    from deeptrace.harness.source_navigation import source_link_candidates
    store = InMemoryEvidenceStore()
    identities = await _seed_evidence(store, [('https://example.com/overview', 'Overview',
        'topic http://127.0.0.1/secret\n topic https://example.com/pricing')])
    fixture = build_gateway_fixture(model_gateway=BatchModel(), evidence_store=store)
    task = ResearchTopicInput(run_id='run-1', thread_id='thread-1', query='topic',
        mode=ResearchMode.WORKFLOW, caller_id='workflow-graph', authorized_evidence_ids=identities)
    rows = await source_link_candidates(task, fixture.context)
    assert [row['url'] for row in rows] == ['https://example.com/pricing']
    frozen = replace(fixture.context, source_evidence_ids=identities)
    assert await source_link_candidates(task, frozen) == []


@pytest.mark.asyncio
async def test_index_following_never_fetches_outside_frozen_corpus():
    from dataclasses import replace
    from deeptrace.domain import ResearchTopicInput, ResearchMode
    from deeptrace.harness.batch_collection import fetch_sources

    index, reference = 'https://example.com/index', 'https://example.com/topic'
    store = InMemoryEvidenceStore()
    identities = await _seed_evidence(store, [(index, 'API Index', f'topic details: {reference}')])
    fixture = build_gateway_fixture(model_gateway=BatchModel(), evidence_store=store)
    task = ResearchTopicInput(run_id='run-1', thread_id='thread-1', query='topic',
        mode=ResearchMode.WORKFLOW, caller_id='workflow-graph', authorized_evidence_ids=identities)
    frozen = replace(fixture.context, source_evidence_ids=identities)
    await fetch_sources({'topic_input': task, 'candidate_urls': [index], 'seen_urls': [reference]}, frozen)
    assert fixture.fetcher.calls == []
