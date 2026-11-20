import json

import pytest
from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_research import build_batch_research_graph
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture

from harness.test_batch_research import BatchModel


@pytest.mark.asyncio
async def test_unique_user_supplied_document_is_read_without_selection_call():
    from dataclasses import replace
    from deeptrace.harness.source_selection import select_sources
    from deeptrace.harness.token_budget import TokenBudgetConfig

    class UnneededModel:
        async def invoke(self, **kwargs):
            pytest.fail('unique explicitly requested document needs no model selection')

    task = ResearchTopicInput(run_id='r', thread_id='t', query='Retry-After',
        original_task='Read https://www.rfc-editor.org/rfc/rfc9110.html',
        mode=ResearchMode.WORKFLOW, caller_id='workflow-graph', evidence_contract_version=3,
        requirements=[{'id':'r1','description':'Retry-After'}])
    result = await select_sources({'topic_input':task, 'candidate_urls':[
        'https://www.rfc-editor.org/rfc/rfc9110.html'], 'source_candidates':[
        {'id':'c1','url':'https://www.rfc-editor.org/rfc/rfc9110.html'}]},
        replace(build_gateway_fixture().context, model_gateway=UnneededModel()), TokenBudgetConfig())
    assert result['candidate_urls'] == ['https://www.rfc-editor.org/rfc/rfc9110.html']
    assert result['batch_read_queries'] == {'r1':['Retry-After']}


@pytest.mark.asyncio
async def test_unique_exact_document_identifier_selects_only_matching_observed_url():
    from dataclasses import replace
    from deeptrace.harness.source_selection import select_sources
    from deeptrace.harness.token_budget import TokenBudgetConfig
    class UnneededModel:
        async def invoke(self, **kwargs):
            pytest.fail('exact document discovery does not need model selection')
    task = ResearchTopicInput(run_id='r',thread_id='t',query='RFC 9110 Retry-After',
        original_task='Only RFC 9110 and RFC 6585', read_terms=['Retry-After','delay-seconds'],
        mode=ResearchMode.WORKFLOW,caller_id='workflow-graph',evidence_contract_version=3,
        requirements=[{'id':'r1','description':'Retry-After'}])
    result = await select_sources({'topic_input':task, 'candidate_urls':[
        'https://example.com/info/rfc9110','https://example.com/info/rfc6585'],
        'source_candidates':[
            {'id':'c1','url':'https://example.com/info/rfc9110'},
            {'id':'c2','url':'https://example.com/info/rfc6585'}]},
        replace(build_gateway_fixture().context,model_gateway=UnneededModel()),TokenBudgetConfig())
    assert result['candidate_urls'] == ['https://example.com/info/rfc9110']
    assert result['batch_read_queries'] == {'r1':['Retry-After','delay-seconds']}


class SelectingModel(BatchModel):
    def __init__(self, selected):
        super().__init__()
        self.selected = selected

    async def invoke(self, *, role, messages, tools=None):
        if "SOURCE_CANDIDATES_JSON:" in str(messages[-1].content):
            return AIMessage(content=json.dumps({"selected": self.selected}))
        return await super().invoke(role=role, messages=messages, tools=tools)


@pytest.mark.asyncio
async def test_one_malformed_selection_can_repair_without_new_candidates_or_budget():
    from deeptrace.harness.source_selection import select_sources
    from deeptrace.harness.model_budget import RunBudgetModelGateway
    from deeptrace.harness.token_budget import TokenBudgetConfig
    from dataclasses import replace
    class Model:
        calls = 0
        async def invoke(self, **kwargs):
            self.calls += 1
            return AIMessage(content='{"selected":["c1"],"read_queries":[{"requirement_id":"r1",":""}]}'
                if self.calls==1 else '{"selected":["c1"]}')
    model=Model()
    budget=RunBudgetModelGateway(model)
    fixture=build_gateway_fixture()
    context=replace(fixture.context,model_gateway=budget)
    task=ResearchTopicInput(run_id='r',thread_id='t',query='topic',mode=ResearchMode.WORKFLOW,
        caller_id='workflow-graph',evidence_contract_version=3,
        requirements=[{'id':'r1','description':'topic'}])
    result=await select_sources({'topic_input':task,'source_candidates':[{'id':'c1','url':'https://example.com/a'}]},
        context,TokenBudgetConfig())
    assert result['candidate_urls']==['https://example.com/a']
    assert budget.used_calls==2


@pytest.mark.asyncio
async def test_selection_repair_rechecks_context_budget():
    from deeptrace.harness.source_selection import select_sources
    from deeptrace.harness.policies.agent_context import message_tokens
    from dataclasses import replace
    from types import SimpleNamespace
    budget=SimpleNamespace(input_budget=100000)
    class Model:
        calls=0
        async def invoke(self, **kwargs):
            self.calls+=1
            budget.input_budget=message_tokens(kwargs['messages'])
            return AIMessage(content='not json')
    model=Model()
    fixture=build_gateway_fixture()
    task=ResearchTopicInput(run_id='r',thread_id='t',query='topic',mode=ResearchMode.WORKFLOW,
        caller_id='workflow-graph',evidence_contract_version=3,
        requirements=[{'id':'r1','description':'topic'}])
    result=await select_sources({'topic_input':task,'source_candidates':[{'id':'c1','url':'https://example.com/a'}]},
        replace(fixture.context,model_gateway=model),budget)
    assert result['stop_reason']=='context_limit'
    assert model.calls==1


async def run_selection(selected):
    fixture = build_gateway_fixture(
        model_gateway=SelectingModel(selected),
        default_search_results=[
            {
                "url": "https://example.com/meeting",
                "title": "Annual conference",
                "snippet": "Call for papers",
            },
            {
                "url": "https://example.com/paper",
                "title": "Measured quantum correlations",
                "snippet": "Original experimental result",
            },
        ],
        pages={
            "https://example.com/meeting": "Conference call for papers.",
            "https://example.com/paper": "Original experimental correlation measurement.",
        },
    )
    task = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="research",
        mode=ResearchMode.PLAN_EXECUTE,
        caller_id="plan-execute-executor",
        source_policy="research_results",
        publication_years=[2026],
    )
    result = await build_batch_research_graph().ainvoke(
        {"topic_input": task}, context=fixture.context
    )
    return fixture, result


@pytest.mark.asyncio
async def test_background_candidates_do_not_consume_fetch_slots():
    fixture, result = await run_selection(["c2"])
    assert fixture.fetcher.calls == ["https://example.com/paper"]
    assert len(result["outcome"].evidence_ids) == 1
    searches = [
        call
        for call in fixture.gateway.calls
        if call["request"].tool.value == "search_web"
    ]
    assert len(searches) == 2


@pytest.mark.asyncio
async def test_selection_cannot_invent_urls_or_unknown_candidate_ids():
    fixture, result = await run_selection(["c99"])
    assert fixture.fetcher.calls == []
    assert result["outcome"].evidence_ids == []


@pytest.mark.asyncio
async def test_eight_long_search_results_remain_complete_json_at_tool_boundary():
    fixture = build_gateway_fixture(
        model_gateway=SelectingModel(["c8"]),
        default_search_results=[
            {
                "url": f"https://example.com/paper-{i}",
                "title": "A long research title " * 20,
                "snippet": "Original experimental research summary. " * 20,
            }
            for i in range(1, 9)
        ],
    )
    task = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="research",
        mode=ResearchMode.PLAN_EXECUTE,
        caller_id="plan-execute-executor",
        source_policy="research_results",
    )
    result = await build_batch_research_graph().ainvoke(
        {"topic_input": task}, context=fixture.context
    )
    assert fixture.fetcher.calls == ["https://example.com/paper-8"]
    assert result["outcome"].evidence_ids


@pytest.mark.asyncio
async def test_scientific_read_keeps_abstract_before_keyword_heavy_references():
    fact = "We discover an order parameter using reduced fidelity susceptibility."
    body = (
        "Published: 27 June 2026\nAbstract\n"
        + fact
        + " Observables characterize symmetry and phase boundaries." * 20
        + "\n\nReferences\n"
        + "research 2026 systems paper.\n" * 400
    )
    fixture = build_gateway_fixture(
        model_gateway=SelectingModel(["c1"]),
        default_search_results=[
            {
                "url": "https://example.com/paper",
                "title": "Order parameter discovery",
                "snippet": fact,
            }
        ],
        pages={"https://example.com/paper": body},
    )
    task = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="research systems paper 2026",
        mode=ResearchMode.PLAN_EXECUTE,
        caller_id="plan-execute-executor",
        source_policy="research_results",
    )
    result = await build_batch_research_graph().ainvoke(
        {"topic_input": task}, context=fixture.context
    )
    assert any(
        fact in p["text"]
        for preview in result["batch_read_previews"]
        for p in preview["passages"]
    )
    assert all(tools is None for _, _, tools in fixture.context.model_gateway.calls)
