from dataclasses import replace
from types import SimpleNamespace

import pytest

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_collection import search_sources
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.graph import _research_input
from deeptrace.harness.state import new_conversation, new_turn
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
async def test_provided_sources_do_not_dispatch_web_search():
    fixture = build_gateway_fixture()
    record = await seed(fixture, 1, 'Checkpoints persist thread state.')
    context = replace(fixture.context, source_evidence_ids=(record.id,))
    task = ResearchTopicInput(run_id='run-1', thread_id='thread-1', query='checkpoints',
        mode=ResearchMode.PLAN_EXECUTE, caller_id='plan-execute-executor')
    result = await search_sources({'topic_input': task}, context)
    assert result['candidate_urls'] == [record.canonical_url]
    assert not fixture.search.calls


@pytest.mark.asyncio
async def test_empty_provided_scope_does_not_fall_back_to_web():
    fixture = build_gateway_fixture()
    context = replace(fixture.context, source_evidence_ids=())
    task = ResearchTopicInput(run_id='run-1', thread_id='thread-1', query='question',
        mode=ResearchMode.WORKFLOW, caller_id='workflow-graph')
    result = await search_sources({'topic_input':task},context)
    assert result['candidate_urls'] == []
    assert not fixture.search.calls


def test_provided_scope_grants_replace_conversation_evidence():
    from datetime import datetime, UTC
    state = {'conversation': new_conversation('thread-1', ResearchMode.WORKFLOW),
             'turn': new_turn('run-1', 'question', ResearchMode.WORKFLOW)}
    state['conversation']['evidence_ids'] = ['outside-source']
    context = HarnessContext('user','workspace',object(),object(),object(),object(),
        SimpleNamespace(now=lambda: datetime.now(UTC)), source_evidence_ids=('provided-source',))
    result = _research_input(state, SimpleNamespace(context=context))
    assert result.prior_evidence_ids == ['provided-source']


def test_combined_capabilities_read_query_preserves_compatibility_condition():
    from deeptrace.harness.batch_collection import reading_query
    from deeptrace.tools.evidence_views import select_source_excerpt
    import json
    from pathlib import Path
    corpus = json.loads((Path(__file__).parents[2] / 'src/deeptrace/evaluation/data/frozen-corpus.json').read_text(encoding='utf-8'))
    body = next(doc['body'] for doc in corpus if doc['id']=='langchain-structured-output')
    query = reading_query('ProviderStrategy structured output support',
                          'combine human-reviewed tool calls with provider-native structured output')
    excerpt = select_source_excerpt(body, query, 3000)
    assert 'simultaneous use of tools and structured output' in excerpt.text


def test_version_boundary_read_keeps_parameter_support_and_default_notes():
    from deeptrace.harness.batch_collection import reading_query
    from deeptrace.tools.evidence_views import select_source_excerpt
    import json
    from pathlib import Path
    corpus = json.loads((Path(__file__).parents[2] / 'src/deeptrace/evaluation/data/frozen-corpus.json').read_text(encoding='utf-8'))
    body = next(doc['body'] for doc in corpus if doc['id']=='langchain-structured-output')
    excerpt = select_source_excerpt(body, reading_query('ProviderStrategy strict version provider support',
        'what is the version and provider-support boundary for strict?'),3000)
    assert 'some providers' in excerpt.text
    assert 'Defaults to' in excerpt.text
