import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage
from application.test_batch_assembly import ResearchModel
from strategies.fixtures import build_gateway_fixture, evaluation_payload_from_view

from deeptrace.application import assembly
from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings
from deeptrace.domain import ResearchMode


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_shared_production_strategies_report_coverage_between_planning_and_writing(tmp_path, monkeypatch, mode):
    class Model(ResearchModel):
        async def invoke(self, *, role, messages, tools=None):
            if role == "supervisor":
                self.calls.append((role, messages, tools))
                return AIMessage(content=json.dumps({"assignments": ["topic-one", "topic-two"],
                    "requirements": [{"id": "r1", "description": "topic facts"}],
                    "query_targets": {"topic-one": ["r1"], "topic-two": ["r1"]}}))
            if role == "evaluator":
                self.calls.append((role, messages, tools))
                return AIMessage(content=json.dumps(evaluation_payload_from_view(str(messages[-1].content),
                    sufficient=True if mode is ResearchMode.WORKFLOW else None)))
            return await super().invoke(role=role, messages=messages, tools=tools)

    model = Model()
    monkeypatch.setattr(assembly, "ChatModelGateway", lambda *args, **kwargs: model)
    settings = Settings("test", "https://example.com/v1", "test", "test", memory_retrieval="lexical")
    assert settings.research_orchestrator == "strategies"
    bundle = assembly.build_harness_runtime(settings, runs_dir=tmp_path)
    fixture = build_gateway_fixture(search_results={
        "topic-one": [{"url": "https://example.com/one", "title": "One"}],
        "topic-two": [{"url": "https://example.com/two", "title": "Two"}],
    }, pages={"https://example.com/one": "topic fact one.", "https://example.com/two": "topic fact two."})
    context = replace(bundle.context_factory("run-1"), tool_gateway=fixture.gateway,
        evidence_store=fixture.evidence_store, memory_store=None, clock=fixture.context.clock, event_sink=fixture.events)
    try:
        result = await bundle.service.invoke(ApplicationResearchRequest(run_id="run-1", thread_id="thread-1",
            question="Research topic facts", mode=mode), config={"configurable": {"thread_id": "thread-1"}}, context=context)
        assert result.research_outcome.mode is mode
        assert result.response_outcome.content
        kinds = [kind for kind, _ in fixture.events.events]
        phases = ["planning.started", "planning.completed", "research.coverage.reviewed",
                  "writing.started", "writing.completed"]
        for phase in phases:
            assert kinds.count(phase) == 1
        assert [kinds.index(phase) for phase in phases] == sorted(kinds.index(phase) for phase in phases)
        assert "evaluation.started" not in kinds
        assert "evaluation.completed" not in kinds
        roles = [role for role, _, _ in model.calls]
        assert ("supervisor" in roles) is (mode is ResearchMode.MULTI_AGENT)
    finally:
        await bundle.aclose()
