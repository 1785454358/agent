"""Production assembly, durable budgets, Harness and Writer on the unified path."""

import json
from dataclasses import replace

import pytest
from application.test_batch_assembly import ResearchModel
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture, evaluation_payload_from_view

from deeptrace.application import assembly
from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings
from deeptrace.domain import ResearchMode


class ControllerModel(ResearchModel):
    review_failure = False

    async def invoke(self, *, role, messages, tools=None):
        if role == "evaluator":
            self.calls.append((role, messages, tools))
            return AIMessage(content=json.dumps(evaluation_payload_from_view(
                str(messages[-1].content), sufficient=True)))
        if role == "responder":
            self.calls.append((role, messages, tools))
            review = "同一份可见原文" in str(messages[-1].content)
            if review and self.review_failure:
                raise RuntimeError("review provider unavailable")
            payload = {"content": "topic fact one.[1]"}
            if review:
                payload["unanswered_points"] = []
            return AIMessage(content=json.dumps(payload))
        return await super().invoke(role=role, messages=messages, tools=tools)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
@pytest.mark.parametrize("review_failure", [False, True])
async def test_production_controller_routes_all_modes_through_writer(tmp_path, monkeypatch, mode, review_failure):
    model = ControllerModel()
    model.review_failure = review_failure
    monkeypatch.setattr(assembly, "ChatModelGateway", lambda *args, **kwargs: model)
    settings = Settings("test", "https://example.com/v1", "test", "test", memory_retrieval="lexical", research_orchestrator="controller")
    assert settings.research_orchestrator == "controller"
    bundle = assembly.build_harness_runtime(settings, runs_dir=tmp_path)
    fixture = build_gateway_fixture(
        search_results={
            "topic-one": [{"url": "https://example.com/one", "title": "one"}],
            "topic-two": [{"url": "https://example.com/two", "title": "two"}],
        }, pages={"https://example.com/one": "topic fact one.",
                  "https://example.com/two": "topic fact two."},
    )
    context = replace(bundle.context_factory("run-1"), tool_gateway=fixture.gateway,
                      evidence_store=fixture.evidence_store, event_sink=fixture.events,
                      memory_store=None, clock=fixture.context.clock)
    try:
        result = await bundle.service.invoke(
            ApplicationResearchRequest(run_id="run-1", thread_id="thread-1",
                                       question="对比 topic 的事实", mode=mode),
            config={"configurable": {"thread_id": "thread-1"}}, context=context)
        assert result.status == ("partial" if review_failure else "completed")
        assert result.research_outcome.mode is mode
        assert result.research_outcome.termination_reason == "completed"
        assert result.research_outcome.read_anchors
        assert result.research_outcome.coverage is None
        assert result.response_outcome.content.strip()
        assert result.response_outcome.citations
        assert sum(role in {"planner", "supervisor"} for role, _, _ in model.calls) == 1
        assert sum(role == "coverage_reviewer" for role, _, _ in model.calls) == 1
        assert sum(role == "evaluator" for role, _, _ in model.calls) == 0
        assert sum(role == "responder" for role, _, _ in model.calls) == 2
    finally:
        await bundle.aclose()


@pytest.mark.asyncio
async def test_application_restart_resumes_controller_subgraph_without_replanning(tmp_path, monkeypatch):
    import asyncio
    from langgraph.errors import NodeCancelledError

    model = ControllerModel()
    monkeypatch.setattr(assembly, "ChatModelGateway", lambda *args, **kwargs: model)
    build_batch = assembly.build_batch_research_graph
    done = asyncio.Event()
    calls = []

    class InterruptedBatch:
        def __init__(self, inner):
            self.inner = inner

        async def ainvoke(self, data, config=None, **kwargs):
            query = data["topic_input"].query
            calls.append(query)
            if query == "topic-two" and calls.count(query) == 1:
                await done.wait()
                await asyncio.sleep(0.15)
                raise asyncio.CancelledError("worker restarted")
            result = await self.inner.ainvoke(data, config=config, **kwargs)
            done.set()
            return result

    monkeypatch.setattr(assembly, "build_batch_research_graph", lambda **kwargs: InterruptedBatch(build_batch(**kwargs)))
    settings = Settings("test", "https://example.com/v1", "test", "test",
                        memory_retrieval="lexical", research_orchestrator="controller")
    fixture = build_gateway_fixture(
        search_results={
            "topic-one": [{"url": "https://example.com/one", "title": "one"}],
            "topic-two": [{"url": "https://example.com/two", "title": "two"}],
        }, pages={"https://example.com/one": "topic fact one.",
                  "https://example.com/two": "topic fact two."})
    request = ApplicationResearchRequest(run_id="run-1", thread_id="thread-1",
                                         question="研究 topic 的事实", mode="multi_agent")
    config = {"configurable": {"thread_id": "thread-1"}}

    def context_for(bundle):
        return replace(bundle.context_factory("run-1"), tool_gateway=fixture.gateway,
                       evidence_store=fixture.evidence_store, event_sink=fixture.events,
                       memory_store=None, clock=fixture.context.clock)

    first = assembly.build_harness_runtime(settings, runs_dir=tmp_path)
    try:
        with pytest.raises((asyncio.CancelledError, NodeCancelledError)):
            await first.service.invoke(request, config=config, context=context_for(first))
    finally:
        await first.aclose()
    restarted = assembly.build_harness_runtime(settings, runs_dir=tmp_path)
    try:
        result = await restarted.service.invoke(request, config=config, context=context_for(restarted))
        assert result.status == "completed"
        assert calls.count("topic-one") == 1
        assert calls.count("topic-two") == 2
        assert sum(role in {"planner", "supervisor"} for role, _, _ in model.calls) == 1
        assert sum(role == "coverage_reviewer" for role, _, _ in model.calls) == 1
    finally:
        await restarted.aclose()


@pytest.mark.asyncio
async def test_old_interrupted_run_is_not_silently_resumed_by_new_algorithm():
    from types import SimpleNamespace
    from deeptrace.application.research import ResearchApplicationService
    class OldCheckpoint:
        async def aget_state(self,config):
            return SimpleNamespace(next=('workflow',),values={'turn':{'run_id':'old-run'}})
        async def ainvoke(self,*args,**kwargs):
            raise AssertionError('old graph must not execute as new flow')
    service=ResearchApplicationService(OldCheckpoint())
    with pytest.raises(ValueError,match='legacy_research_checkpoint'):
        await service.invoke(ApplicationResearchRequest(run_id='old-run',thread_id='old-thread',
            question='Compare rules',mode=ResearchMode.WORKFLOW),
            config={'configurable':{'thread_id':'old-thread'}},
            context=build_gateway_fixture().context)
