import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from deeptrace.application import assembly
from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings
from harness.test_batch_research import BatchModel
from strategies.fixtures import build_gateway_fixture, evaluation_payload_from_view


class ResearchModel(BatchModel):
    async def invoke(self, *, role, messages, tools=None):
        if role == "researcher":
            return await super().invoke(role=role, messages=messages, tools=tools)
        self.calls.append((role, messages, tools))
        if role == "planner":
            return AIMessage(content=json.dumps({"queries": ["topic-one", "topic-two"],
                "requirements": [{"id": "r1", "description": "topic 的事实"}],
                "query_targets": {"topic-one": ["r1"], "topic-two": ["r1"]}}))
        if role == "evaluator":
            return AIMessage(content=json.dumps(evaluation_payload_from_view(str(messages[-1].content))))
        if role == "responder":
            return AIMessage(content=json.dumps({"content": "原文记录了 topic 的两个事实：one 和 two。[1][2]"}))
        raise AssertionError(role)


@pytest.mark.asyncio
async def test_production_assembly_reaches_cited_answer_with_one_synthesis_per_topic(tmp_path, monkeypatch):
    model = ResearchModel()
    monkeypatch.setattr(assembly, "ChatModelGateway", lambda *args, **kwargs: model)
    settings = Settings("test", "https://example.com/v1", "test", "test", memory_retrieval="lexical")
    bundle = assembly.build_harness_runtime(settings, runs_dir=tmp_path)
    fixture = build_gateway_fixture(search_results={
        "topic-one": [{"url": "https://example.com/one", "title": "one", "snippet": "topic"}],
        "topic-two": [{"url": "https://example.com/two", "title": "two", "snippet": "topic"}],
    }, pages={"https://example.com/one": "topic fact one.", "https://example.com/two": "topic fact two."})
    context = replace(bundle.context_factory("run-1"), tool_gateway=fixture.gateway,
                      evidence_store=fixture.evidence_store, event_sink=fixture.events,
                      memory_store=None, clock=fixture.context.clock)
    try:
        result = await bundle.service.invoke(ApplicationResearchRequest(run_id="run-1", thread_id="thread-1",
            question="研究 topic 的事实", mode="plan_execute"),
            config={"configurable": {"thread_id": "thread-1"}}, context=context)
        assert result.status == "completed"
        assert len(result.response_outcome.citations) == 2
        assert [r for r, _, _ in model.calls] == ["planner", "researcher", "researcher", "evaluator", "responder"]
    finally:
        await bundle.aclose()


@pytest.mark.asyncio
async def test_factory_reuses_one_run_budget_across_context_recreation(tmp_path, monkeypatch):
    model = ResearchModel()
    monkeypatch.setattr(assembly, "ChatModelGateway", lambda *args, **kwargs: model)
    bundle = assembly.build_harness_runtime(Settings("test", "https://example.com/v1", "test", "test", memory_retrieval="lexical"), runs_dir=tmp_path)
    try:
        first = bundle.context_factory("run-1").model_gateway
        second = bundle.context_factory("run-1").model_gateway
        third = bundle.context_factory("run-2").model_gateway
        assert first is second
        assert first is not third
        assert hasattr(first, "research_exhausted")
    finally:
        await bundle.aclose()
