"""Scholarly acquisition reaches full text and reads actual assigned questions."""

import json
import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import ResearchMode, ResearchRequirement, ResearchTopicInput
from deeptrace.harness.batch_research import build_batch_research_graph
from strategies.fixtures import build_gateway_fixture


class PaperSelector:
    async def invoke(self, **kwargs):
        return AIMessage(content=json.dumps({
            "selected": ["c1"], "read_queries": [{"requirement_id": "r1",
                "query": "experimental setup model MATH benchmark inference token budget results limitations"}],
        }))


def paper_task(max_pages=8):
    return ResearchTopicInput(
        run_id="run-1", thread_id="thread-1", query="test-time compute scaling",
        mode=ResearchMode.MULTI_AGENT, caller_id="researcher-0",
        evidence_contract_version=3, source_policy="research_results", publication_years=[2024, 2025],
        requirements=[{"id": "r1", "description": "Compare experimental setup and budget results"}],
        target_requirement_ids=["r1"], max_pages=max_pages,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["invalid_pdf", "pdf_encrypted", "pdf_page_limit",
    "pdf_page_stream_limit", "pdf_text_limit", "pdf_text_unavailable", "pdf_extraction_timeout"])
async def test_unreadable_pdf_does_not_prevent_reading_other_selected_paper(code, monkeypatch):
    from deeptrace.tools.scraper import WebFetchError
    bad, good = "https://example.com/unreadable.pdf", "https://example.com/full-paper"
    class SelectBoth(PaperSelector):
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({"selected": ["c1", "c2"]}))
    fixture = build_gateway_fixture(model_gateway=SelectBoth(),
        default_search_results=[{"url": bad, "title": "Paper A"}, {"url": good, "title": "Paper B"}],
        pages={good: "Published: 6 August 2024. Experimental setup: MODEL_B on MATH with 64 samples."})
    fetch = fixture.fetcher.fetch
    failures = []
    async def external_fetch(url):
        if url == bad:
            failures.append(url)
            raise WebFetchError(code, "Unreadable PDF")
        return await fetch(url)
    monkeypatch.setattr(fixture.fetcher, "fetch", external_fetch)
    state = await build_batch_research_graph().ainvoke({"topic_input": paper_task()}, context=fixture.context)
    assert failures == [bad]
    assert state["outcome"].read_anchors
    assert any("MODEL_B" in json.dumps(row) for row in state["batch_read_previews"])
    assert any(error.code == code for error in state["outcome"].errors)


@pytest.mark.asyncio
@pytest.mark.parametrize("max_pages", [1, 8])
async def test_abstract_page_follows_only_observed_fulltext_for_same_paper_within_budget(max_pages):
    abstract = "https://arxiv.org/abs/2408.03314"
    full = "https://arxiv.org/html/2408.03314v1"
    unrelated = "https://arxiv.org/html/2501.19393v1"
    fixture = build_gateway_fixture(model_gateway=PaperSelector(),
        default_search_results=[{"url": abstract, "title": "Compute scaling"}], pages={
            abstract: "Published: 6 August 2024\nAbstract: We study compute.\n"
                      "Original research links (HTML anchors):\n" + unrelated + "\n" + full,
            full: "Published: 6 August 2024\nExperimental setup: PaLM-2, MATH, fixed sample budget.",
        })
    result = await build_batch_research_graph().ainvoke({"topic_input": paper_task(max_pages)}, context=fixture.context)
    assert fixture.fetcher.calls == ([abstract] if max_pages == 1 else [abstract, full])
    if max_pages > 1:
        assert result["batch_read_previews"][0]["url"] == full
    assert result["pages_fetched"] <= max_pages


@pytest.mark.asyncio
async def test_scholarly_reader_uses_assigned_experimental_query_not_only_opening_and_broad_topic():
    url = "https://example.com/paper"
    body = ("Published: 6 August 2024\nAbstract: broad topic.\n\n" + "Unrelated discussion.\n\n" * 400
            + "## Experimental setup\nWe evaluate MODEL_X on MATH using 128 candidate samples.\n\n"
            + "## Limitations\nResults depend on verifier accuracy and problem difficulty.")
    fixture = build_gateway_fixture(model_gateway=PaperSelector(),
        default_search_results=[{"url": url, "title": "Compute scaling"}], pages={url: body})
    result = await build_batch_research_graph().ainvoke({"topic_input": paper_task()}, context=fixture.context)
    reads = [call["request"].arguments for call in fixture.gateway.calls
             if call["request"].tool.value == "read_evidence"]
    assert any("experimental setup model MATH" in r.get("query", "") for r in reads)
    assert any("MODEL_X" in json.dumps(p) for p in result["batch_read_previews"])
    assert result["outcome"].read_anchors


@pytest.mark.asyncio
async def test_chinese_requirements_still_locate_experiments_in_english_original_without_model_hint():
    url = "https://example.com/english-paper"
    body = "Published: 6 August 2024. Abstract.\n\n" + "Unrelated background.\n\n" * 500
    body += "## Experimental setup\n\nModel MODEL_X is evaluated on benchmark MATH with 128 candidate samples."
    class NoHints(PaperSelector):
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({"selected": ["c1"]}))
    fixture = build_gateway_fixture(model_gateway=NoHints(),
        default_search_results=[{"url": url, "title": "Original paper"}], pages={url: body})
    task = paper_task().model_copy(update={"requirements": [
        ResearchRequirement(
            id="r1", description="列出模型、评测集、计算预算口径与主要结果")]})
    result = await build_batch_research_graph().ainvoke({"topic_input": task}, context=fixture.context)
    assert any("MODEL_X" in json.dumps(row) for row in result["batch_read_previews"])


@pytest.mark.asyncio
async def test_production_task_budget_can_resolve_abstract_without_displacing_other_papers():
    from deeptrace.domain import ResearchInput
    from deeptrace.research.adapters import build_contract_and_plan
    from deeptrace.research.execution import execute_task

    abstract, full = 'https://arxiv.org/abs/2408.03314', 'https://arxiv.org/html/2408.03314v1'
    others = ['https://example.com/second-paper', 'https://example.com/third-paper']
    class ThreeSources(PaperSelector):
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({'selected': ['c1', 'c2', 'c3']}))
    fixture = build_gateway_fixture(model_gateway=ThreeSources(),
        default_search_results=[{'url': url, 'title': 'Original study'} for url in [abstract, *others]],
        pages={abstract: 'Abstract.\nOriginal research links (HTML anchors):\n' + full,
               full: 'Published: 6 August 2024. Full experiment, model and MATH setup.',
               **{url: 'Published: 7 August 2024. Independent original experiment.' for url in others}})
    task = paper_task()
    contract, plan = build_contract_and_plan(run_id='run-1', question='Compare three original studies',
        requirements=task.requirements, queries=[task.query], source_policy='research_results')
    outcome = await execute_task(task=plan.tasks[0], contract=contract,
        research_input=ResearchInput(run_id='run-1', thread_id='thread-1', question=contract.goal,
                                     current_date='2026-11-17', timezone='Asia/Shanghai'),
        context=fixture.context, topic_graph=build_batch_research_graph(),
        authorized_evidence_ids=[], mode=ResearchMode.MULTI_AGENT)
    assert full in fixture.fetcher.calls
    read_ids = {a.evidence_id for a in outcome.read_anchors}
    read_urls = {(await fixture.evidence_store.get(fixture.context.workspace_id, i)).canonical_url for i in read_ids}
    assert read_urls == {full, *others}
