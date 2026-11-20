"""Discovery hints cannot hide current originals; v3 hands reads off intact."""

import json

import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_collection import search_sources
from deeptrace.harness.batch_research import build_batch_research_graph
from harness.test_batch_research import BatchModel


def topic(**kwargs):
    return ResearchTopicInput(
        run_id="run-1", thread_id="thread-1", query="widget recovery docs",
        mode=ResearchMode.WORKFLOW, caller_id="workflow-graph", **kwargs,
    )


@pytest.mark.asyncio
async def test_obsolete_guessed_host_does_not_hide_current_official_documentation():
    query = "widget recovery docs"
    url = "https://current.example.com/widget/recovery"
    model = BatchModel()
    fixture = build_gateway_fixture(
        model_gateway=model,
        search_results={query: [{"url": url, "title": "Widget recovery"}]},
        default_search_results=[], pages={url: "Recovery requires a durable backend."},
    )
    result = await build_batch_research_graph().ainvoke({"topic_input": topic(
        source_domains=["obsolete.example.com"],
        search_queries=[query, "widget backend details"],
        evidence_contract_version=3,
    )}, context=fixture.context)

    assert fixture.search.calls[0] == query
    assert len(fixture.search.calls) == 2
    assert fixture.fetcher.calls == [url]
    assert result["outcome"].read_anchors
    assert len(model.calls) == 1
    assert "SOURCE_CANDIDATES_JSON:" in str(model.calls[0][1][-1].content)


@pytest.mark.asyncio
async def test_multiple_domain_hints_are_disjunctive_and_leave_primary_discovery_open():
    fixture = build_gateway_fixture(default_search_results=[])
    await search_sources({"topic_input": topic(
        search_queries=["primary", "secondary"],
        source_domains=["docs.example.com", "reference.example.org"],
    )}, fixture.context)
    assert fixture.search.calls == [
        "primary", "(site:docs.example.com OR site:reference.example.org) secondary",
    ]


@pytest.mark.asyncio
async def test_single_seed_keeps_broad_and_hinted_discovery_within_two_calls():
    fixture = build_gateway_fixture(default_search_results=[])
    await search_sources({"topic_input": topic(
        source_domains=["docs.example.com"],
    )}, fixture.context)
    assert fixture.search.calls == [
        "widget recovery docs", "site:docs.example.com widget recovery docs",
    ]


@pytest.mark.asyncio
async def test_explicit_document_version_narrows_domain_hint_within_two_searches():
    fixture=build_gateway_fixture(default_search_results=[])
    await search_sources({'topic_input':topic(original_task='仅依据 Python 3.11 官方文档回答',
        source_domains=['docs.python.org'])},fixture.context)
    assert len(fixture.search.calls)==2
    assert 'site:docs.python.org/3.11' in fixture.search.calls[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["根据", "按照", "基于"])
async def test_natural_language_version_constraint_reaches_discovery(prefix):
    fixture = build_gateway_fixture(default_search_results=[])
    await search_sources({"topic_input": topic(
        original_task=prefix + " Python 3.11 官方文档，诊断任务异常并给出修复步骤。",
        source_domains=["docs.python.org"],
    )}, fixture.context)
    assert len(fixture.search.calls) == 2
    assert "site:docs.python.org/3.11" in fixture.search.calls[1]


@pytest.mark.asyncio
async def test_missing_domain_hint_can_use_discovered_version_path_without_extra_calls():
    broad='widget recovery docs'
    narrow='site:docs.python.org/3.11/library/asyncio-task.html '+broad
    fixture=build_gateway_fixture(search_results={
        broad:[{'url':'https://docs.python.org/3.15/library/asyncio-task.html','title':'Python 3.15'}],
        narrow:[{'url':'https://docs.python.org/3.11/library/asyncio-task.html','title':'Python 3.11'}]})
    result=await search_sources({'topic_input':topic(original_task='仅依据 Python 3.11 官方文档回答')},fixture.context)
    assert fixture.search.calls==[broad,narrow]
    assert 'https://docs.python.org/3.11/library/asyncio-task.html' in result['candidate_urls']


@pytest.mark.asyncio
async def test_matching_version_on_another_page_does_not_disable_target_path_recovery():
    broad = 'widget recovery docs'
    narrow = 'site:docs.python.org/3.11/library/asyncio-task.html ' + broad
    fixture = build_gateway_fixture(search_results={broad: [
        {'url': 'https://docs.python.org/3.11/library/asyncio-exceptions.html', 'title': 'Exceptions'},
        {'url': 'https://docs.python.org/3.15/library/asyncio-task.html', 'title': 'Tasks'},
    ], narrow: [{'url': 'https://docs.python.org/3.11/library/asyncio-task.html', 'title': 'Tasks'}]})
    result = await search_sources({'topic_input': topic(
        original_task='仅依据 Python 3.11 官方文档回答')}, fixture.context)
    assert fixture.search.calls == [broad, narrow]
    assert 'https://docs.python.org/3.11/library/asyncio-task.html' in result['candidate_urls']


@pytest.mark.asyncio
async def test_requested_version_is_kept_before_merged_candidate_cap():
    broad = 'widget recovery docs'
    hinted = 'site:docs.python.org/3.11 ' + broad
    exact = 'https://docs.python.org/3.11/library/asyncio-task.html'
    stale = [{'url': f'https://docs.python.org/3.15/page-{i}', 'title': 'Latest'} for i in range(8)]
    fixture = build_gateway_fixture(search_results={
        broad: stale, hinted: [*stale[:7], {'url': exact, 'title': 'Version 3.11'}]})
    result = await search_sources({'topic_input': topic(
        original_task='仅依据 Python 3.11 官方文档回答',
        source_domains=['docs.python.org'])}, fixture.context)
    assert exact in result['candidate_urls']
    assert result['candidate_urls'][0] == exact
    assert len(result['candidate_urls']) <= 8


@pytest.mark.asyncio
async def test_versioned_api_index_follows_observed_reference_before_reading():
    index = "https://docs.example.com/3.11/library/asyncio-api-index.html"
    reference = "https://docs.example.com/3.11/library/asyncio-task.html"
    fixture = build_gateway_fixture(
        model_gateway=BatchModel(),
        default_search_results=[{"url": index, "title": "High-level API Index"}],
        pages={index: "# High-level API Index\n" + "\n".join(
            f"[Other API {i}](https://docs.example.com/3.11/library/other-{i}.html)"
            for i in range(20)
        ) + f"\n[Task cancellation and gather]({reference})",
        reference: "Task cancellation delivers CancelledError. Gather leaves siblings running."},
    )
    result = await build_batch_research_graph().ainvoke({"topic_input": ResearchTopicInput(
        run_id="run-1", thread_id="thread-1", query="gather task cancellation",
        mode=ResearchMode.PLAN_EXECUTE, caller_id="plan-execute-executor",
        original_task="根据 Python 3.11 官方文档解释 gather task cancellation",
        evidence_contract_version=3,
    )}, context=fixture.context)
    assert fixture.fetcher.calls == [index, reference]
    bodies = [await fixture.evidence_store.read_body("workspace-1", identity)
              for identity in result["outcome"].evidence_ids]
    assert any("Gather leaves siblings running" in body for body in bodies)


@pytest.mark.asyncio
@pytest.mark.parametrize("selected,expected", [(["c2"], ["https://example.com/manual"]), (["c99"], [])])
async def test_v3_selection_rejects_irrelevant_discovery_and_cannot_invent_candidates(selected, expected):
    model = BatchModel([json.dumps({"selected": selected})])
    fixture = build_gateway_fixture(
        model_gateway=model,
        default_search_results=[
            {"url": "https://example.com/unrelated", "title": "Readers and Writers Book Club"},
            {"url": "https://example.com/manual", "title": "Widget recovery reference manual"},
        ],
    )
    result = await build_batch_research_graph().ainvoke({"topic_input": topic(
        evidence_contract_version=3, original_task="Explain recovery using official documentation",
    )}, context=fixture.context)
    assert fixture.fetcher.calls == expected
    assert len(model.calls) == (1 if expected else 2)
    assert "SOURCE_CANDIDATES_JSON:" in str(model.calls[0][1][-1].content)
    assert not result["outcome"].research_findings


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_v3_retains_later_requirement_reads_without_a_branch_summary(mode):
    model = BatchModel()
    url = "https://example.com/manual"
    body = "Ordinary execution uses request state.\n\n" * 150 + (
        "RECOVERY_FACT: a restart needs durable storage, not the memory backend.\n\n" * 25
    )
    fixture = build_gateway_fixture(
        model_gateway=model, default_search_results=[{"url": url, "title": "Manual"}],
        pages={url: body},
    )
    task = topic(
        evidence_contract_version=3,
        requirements=[
            {"id": "r1", "description": "Ordinary execution request state"},
            {"id": "r2", "description": "restart durable storage memory backend"},
        ], target_requirement_ids=["r1", "r2"],
    ).model_copy(update={"mode": mode})
    result = await build_batch_research_graph().ainvoke(
        {"topic_input": task}, context=fixture.context,
    )
    assert len(model.calls) == 1
    assert "SOURCE_CANDIDATES_JSON:" in str(model.calls[0][1][-1].content)
    outcome = result["outcome"]
    assert outcome.plan_complete
    assert outcome.agent_outcome.stop_reason == "completed"
    assert outcome.research_findings == []
    assert outcome.read_anchors
    assert not any(code.startswith("synthesis_window_") for code in outcome.research_finding_diagnostics)
    text = "\n".join(p["text"] for v in result["batch_read_previews"] for p in v["passages"])
    assert "RECOVERY_FACT" in text
    for anchor in outcome.read_anchors:
        assert 0 <= anchor.start < anchor.end <= len(body)
