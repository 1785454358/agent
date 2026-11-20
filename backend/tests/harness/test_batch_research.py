"""A page must reach model synthesis without model-directed fetch/read turns."""
import json

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_research import build_batch_research_graph
from strategies.fixtures import build_gateway_fixture


@pytest.mark.asyncio
async def test_reused_source_keeps_original_language_read_terms():
    from strategies.test_reference_materials import seed
    fixture = build_gateway_fixture(model_gateway=BatchModel())
    body = "unrelated. " * 1000 + "\n\nRetry-After = HTTP-date / delay-seconds\n"
    record = await seed(fixture, 1, body)
    task = ResearchTopicInput(run_id='run-1',thread_id='thread-1',query='header syntax',
        mode=ResearchMode.WORKFLOW,caller_id='workflow-graph',evidence_contract_version=3,
        requirements=[{'id':'r1','description':'响应头的两种格式'}],
        target_requirement_ids=['r1'],read_terms=['Retry-After','delay-seconds'],
        authorized_evidence_ids=[record.id])
    from deeptrace.harness.batch_collection import read_sources
    result = await read_sources({'topic_input':task,'batch_selected_ids':[record.id]},fixture.context)
    assert any('Retry-After' in body[a.start:a.end] for a in result['read_anchors'])


class BatchModel:
    def __init__(self, replies=None):
        self.calls = []
        self.replies = list(replies or [])

    async def invoke(self, *, role, messages, tools=None):
        self.calls.append((role, messages, tools))
        if self.replies:
            return AIMessage(content=self.replies.pop(0))
        prompt = str(messages[-1].content)
        if "SOURCE_CANDIDATES_JSON:\n" in prompt:
            rows = json.loads(prompt.split("SOURCE_CANDIDATES_JSON:\n", 1)[1])
            return AIMessage(content=json.dumps({"selected": [row["id"] for row in rows]}))
        if "BATCH_EVIDENCE_JSON:\n" not in prompt:
            return AIMessage(content='{"summary":"待取材","findings":[]}')
        view = json.JSONDecoder().raw_decode(prompt.split("BATCH_EVIDENCE_JSON:\n", 1)[1])[0]
        return AIMessage(content=json.dumps({
            "summary": "已整理实际读取的来源",
            "findings": [{"claim": p["text"], "refs": [p["ref"]], "confidence": 0.9}
                         for p in view["passages"][:5]],
        }, ensure_ascii=False))


def graph():
    return build_batch_research_graph()


async def run(fixture, **updates):
    task = ResearchTopicInput(run_id="run-1", thread_id="thread-1", query="topic",
                              mode=ResearchMode.PLAN_EXECUTE,
                              caller_id="plan-execute-executor", max_pages=8,
                              **updates)
    return await graph().ainvoke({"topic_input": task}, context=fixture.context)


@pytest.mark.asyncio
async def test_batch_collects_three_sources_before_one_model_call_with_real_quotes():
    model = BatchModel()
    fixture = build_gateway_fixture(model_gateway=model, search_results={"topic": [
        {"url": f"https://example.com/{n}", "title": str(n), "snippet": "topic"}
        for n in range(3)]}, pages={f"https://example.com/{n}": f"topic fact {n}." for n in range(3)})
    result = await run(fixture)
    outcome = result["outcome"]
    assert len(outcome.evidence_ids) == 3
    assert len(model.calls) == 1
    assert outcome.agent_outcome.iterations == 1
    assert outcome.plan_complete
    assert len(outcome.research_findings) == 3
    for finding in outcome.research_findings:
        support = finding.supports[0]
        body = await fixture.evidence_store.read_body("workspace-1", support.evidence_id)
        assert support.quote == body[support.start:support.end]
    assert [c["request"].tool.value for c in fixture.gateway.calls] == [
        "search_web", *(["fetch_page"] * 3), *(["read_evidence"] * 3)]


@pytest.mark.asyncio
async def test_duplicate_url_and_failed_page_do_not_fill_the_source_target():
    model = BatchModel()
    urls = ["https://example.com/bad", "https://example.com/a", "https://example.com/a",
            "https://example.com/b", "https://example.com/c"]
    fixture = build_gateway_fixture(model_gateway=model,
        search_results={"topic": [{"url": u, "title": "t", "snippet": "topic"} for u in urls]},
        fetch_failures={urls[0]: "empty"})
    result = await run(fixture)
    assert len(result["outcome"].evidence_ids) == 3
    assert fixture.fetcher.calls.count("https://example.com/a") == 1
    assert fixture.fetcher.calls.count("https://example.com/bad") == 1
    assert len(model.calls) == 1
    assert result["pages_fetched"] == 3


@pytest.mark.asyncio
async def test_existing_source_is_read_without_fetching_or_charging_a_new_page():
    model = BatchModel()
    fixture = build_gateway_fixture(model_gateway=model, search_results={"topic": [
        {"url": "https://example.com/a", "title": "t", "snippet": "topic"}]})
    first = await run(fixture)
    ids = first["outcome"].evidence_ids
    fixture.fetcher.calls.clear()
    result = await run(fixture, authorized_evidence_ids=ids)
    assert result["outcome"].read_anchors
    assert fixture.fetcher.calls == []
    assert result["pages_fetched"] == 0


@pytest.mark.asyncio
async def test_no_sources_needs_no_model_synthesis_and_preserves_the_gap():
    model = BatchModel()
    fixture = build_gateway_fixture(model_gateway=model, default_search_results=[])
    result = await run(fixture)
    assert model.calls == []
    assert not result["outcome"].evidence_ids
    assert result["outcome"].agent_outcome.status != "completed"


@pytest.mark.asyncio
async def test_invalid_findings_are_repaired_once_then_leave_original_evidence_available():
    model = BatchModel(['{"summary":"bad","findings":[{"claim":"unsupported","refs":[],"confidence":1}]}'] * 3)
    fixture = build_gateway_fixture(model_gateway=model, default_search_results=[
        {"url": "https://example.com/a", "title": "t", "snippet": "topic"}])
    result = await run(fixture)
    assert len(model.calls) == 2
    assert result["outcome"].research_findings == []
    assert result["outcome"].read_anchors
    assert "batch_synthesis_invalid" in result["outcome"].research_finding_diagnostics


@pytest.mark.asyncio
async def test_synthesis_cannot_cite_an_acquired_reference_omitted_from_its_input():
    from deeptrace.harness.batch_synthesis import synthesize_findings
    from deeptrace.harness.token_budget import TokenBudgetConfig
    model = BatchModel()
    fixture = build_gateway_fixture(model_gateway=model, search_results={"topic": [
        {"url": "https://example.com/a", "title": "a", "snippet": "topic"},
        {"url": "https://example.com/b", "title": "b", "snippet": "topic"}]},
        pages={"https://example.com/a": "topic fact a.", "https://example.com/b": "topic fact b."})
    state = await run(fixture)
    visible = state["batch_read_previews"][0]
    hidden = state["batch_read_previews"][1]["passages"][0]["ref"]
    model.replies = [json.dumps({"summary": "guess", "findings": [
        {"claim": "topic fact b.", "refs": [hidden], "confidence": 1}]})]
    result = await synthesize_findings({**state, "iteration": 0,
        "batch_read_previews": [visible]}, fixture.context, TokenBudgetConfig())
    assert result.get("synthesis_feedback")
    assert "research_findings" not in result


@pytest.mark.asyncio
async def test_synthesis_transport_failure_keeps_sources_and_a_structured_error():
    from deeptrace.domain import ErrorCategory
    from deeptrace.harness.model_gateway import ModelCallError

    class UnavailableModel(BatchModel):
        async def invoke(self, **kwargs):
            raise ModelCallError(ErrorCategory.TRANSIENT)

    fixture = build_gateway_fixture(model_gateway=UnavailableModel(), default_search_results=[
        {"url": "https://example.com/a", "title": "a", "snippet": "topic"}])
    result = await run(fixture)
    agent = result["outcome"].agent_outcome
    assert result["outcome"].read_anchors
    assert agent.stop_reason == "model_error"
    assert agent.errors[0].code == "model_error"
    assert agent.errors[0].category is ErrorCategory.TRANSIENT
