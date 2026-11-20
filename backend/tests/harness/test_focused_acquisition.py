"""Host acquisition must actually retrieve every planned detail."""

import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_collection import search_sources
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.source_selection import select_sources
from deeptrace.harness.token_budget import TokenBudgetConfig
from harness.test_batch_research import BatchModel


def topic(**updates):
    return ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="TaskGroup",
        caller_id="plan-execute-executor",
        mode=ResearchMode.PLAN_EXECUTE,
        **updates,
    )


@pytest.mark.asyncio
async def test_source_domain_hint_guides_complementary_search_without_becoming_evidence():
    fixture = build_gateway_fixture(model_gateway=BatchModel())
    task = topic(search_queries=["Alpha", "Beta"], source_domains=["docs.example.com"])
    result = await search_sources({"topic_input": task}, fixture.context)
    assert fixture.search.calls == [
        "Alpha",
        "site:docs.example.com Beta",
    ]
    assert not result.get("evidence_ids")


def test_source_domain_hint_survives_branch_context():
    from deeptrace.strategies.model_io import branch_context

    result = branch_context(
        {"research_brief": {"source_domains": ["docs.example.com"]}}
    )
    assert topic(**result).source_domains == ["docs.example.com"]


@pytest.mark.asyncio
async def test_scoped_docs_prefer_matching_versions_without_fetching_known_wrong_versions():
    task = topic(original_task='Python 3.11 official docs', source_domains=['docs.python.org'])
    matching = 'https://docs.python.org/3.11/library/tasks.html'
    result = await select_sources({'topic_input': task, 'candidate_urls': [
        'https://docs.python.org/3.15/library/tasks.html', matching]}, object(), TokenBudgetConfig())
    assert result['candidate_urls'] == [matching]


@pytest.mark.asyncio
async def test_general_acquisition_uses_both_complementary_queries():
    fixture = build_gateway_fixture(
        model_gateway=BatchModel(),
        search_results={
            "Alpha": [{"url": "https://example.com/alpha", "title": "Alpha"}],
            "Beta": [{"url": "https://example.com/beta", "title": "Beta"}],
        },
        pages={
            "https://example.com/alpha": "Alpha fact.",
            "https://example.com/beta": "Beta fact.",
        },
    )
    result = await build_batch_research_graph().ainvoke(
        {"topic_input": topic(search_queries=["Alpha", "Beta"])},
        context=fixture.context,
    )
    assert set(fixture.fetcher.calls) == {
        "https://example.com/alpha",
        "https://example.com/beta",
    }
    assert len(result["batch_read_previews"]) == 2


@pytest.mark.asyncio
async def test_each_requirement_gets_its_own_authorized_read_window():
    url = "https://example.com/asyncio"
    body = ("TaskGroup waits for its children.\n\n" * 180) + (
        "gather propagates errors without cancelling siblings.\n\n" * 30
    )
    fixture = build_gateway_fixture(
        model_gateway=BatchModel(),
        default_search_results=[{"url": url, "title": "Asyncio"}],
        pages={url: body},
    )
    task = topic(
        requirements=[
            {"id": "r1", "description": "TaskGroup children"},
            {"id": "r2", "description": "gather propagates errors"},
        ],
        target_requirement_ids=["r1", "r2"],
    )
    result = await build_batch_research_graph().ainvoke(
        {"topic_input": task}, context=fixture.context
    )
    texts = [
        p["text"]
        for preview in result["batch_read_previews"]
        for p in preview["passages"]
    ]
    assert any(
        "gather propagates errors without cancelling siblings." in text
        for text in texts
    )
    assert any("TaskGroup waits" in text for text in texts)
    assert len(result["read_anchors"]) >= 2


@pytest.mark.asyncio
async def test_named_version_is_preferred_without_treating_url_as_verified_evidence():
    task = topic(original_task="Python 3.11 TaskGroup")
    urls = [
        "https://docs.example.com/3/library/task.html",
        "https://docs.example.com/3.11/library/task.html",
    ]
    fixture = build_gateway_fixture(model_gateway=BatchModel())
    result = await select_sources(
        {"topic_input": task, "candidate_urls": urls},
        fixture.context,
        TokenBudgetConfig(),
    )
    assert result.get("candidate_urls") == [urls[1], urls[0]]
