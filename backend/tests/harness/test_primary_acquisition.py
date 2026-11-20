"""Discovery diversity and bounded original-source chasing use real gateway calls."""
import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_research import build_batch_research_graph
from harness.test_source_selection import SelectingModel


def topic(max_pages=8):
    return ResearchTopicInput(run_id='run-1', thread_id='thread-1', query='quantum correlations 2026',
        mode=ResearchMode.PLAN_EXECUTE, caller_id='plan-execute-executor',
        source_policy='research_results', publication_years=[2026], max_pages=max_pages)


@pytest.mark.asyncio
async def test_recall_candidates_are_not_crowded_out_by_advanced_results():
    task = topic()
    fixture = build_gateway_fixture(model_gateway=SelectingModel([]), search_results={
        task.query: [{'url': f'https://example.com/recall-{i}', 'title': 'paper'} for i in range(8)],
        task.query + ' original research paper -conference -workshop -review': [
            {'url': f'https://example.com/advanced-{i}', 'title': 'paper'} for i in range(8)],
    })
    result = await build_batch_research_graph().ainvoke({'topic_input': task}, context=fixture.context)
    urls = [c['url'] for c in result['source_candidates']]
    assert len(urls) == 12
    assert 'https://example.com/recall-5' in urls
    assert 'https://example.com/advanced-5' in urls


@pytest.mark.asyncio
async def test_validated_complementary_queries_replace_near_duplicate_discovery_calls():
    task = topic().model_copy(update={'search_queries':['Bose gas coherence 2026 paper','quantum quench experiment 2026 paper']})
    fixture = build_gateway_fixture(model_gateway=SelectingModel([]), default_search_results=[])
    await build_batch_research_graph().ainvoke({'topic_input':task}, context=fixture.context)
    searches = [c['request'].arguments['query'] for c in fixture.gateway.calls if c['request'].tool.value=='search_web']
    assert searches == task.search_queries


@pytest.mark.asyncio
@pytest.mark.parametrize('max_pages,followed', [(8, True), (1, False)])
async def test_news_paper_link_is_followed_once_and_within_page_budget(max_pages, followed):
    report = 'https://example.com/news'
    paper = 'https://doi.org/10.1234/example.2026'
    model = SelectingModel(['c1'])
    fixture = build_gateway_fixture(model_gateway=model,
        default_search_results=[{'url': report, 'title': 'Lab report', 'snippet': 'Original experiment'}],
        pages={report: 'Source type (HTML metadata): NewsArticle\nPublished (HTML metadata): 2026-06-27\n'
               'Researchers report a correlation.\nOriginal research links (HTML anchors):\n' + paper,
               paper: 'Published: 4 May 2026\nAbstract: We measured correlations under cryogenic conditions.'})
    result = await build_batch_research_graph().ainvoke({'topic_input': topic(max_pages)}, context=fixture.context)
    assert fixture.fetcher.calls == ([report, paper] if followed else [report])
    assert result['pages_fetched'] <= max_pages
    if followed:
        first = result['batch_read_previews'][0]
        assert first['url'] == paper
    assert len(model.calls) == 0  # Selected originals go directly to parent evaluation.
