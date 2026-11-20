"""Semantic routing is exercised through the compiled production session graph."""

import asyncio
import json

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import NodeCancelledError
import pytest

from deeptrace.api import ResearchRequest, _record_to_response
from deeptrace.application.research import ApplicationResearchRequest, ResearchApplicationService
from deeptrace.domain import ResearchMode, ResearchOutcome, ResponseMode, ResponseOutcome
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.registry import StrategyRegistry, StrategyRegistration, ResponseGraphRegistry, ResponseRegistration
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.model_budget import BudgetStateUnavailable
from deeptrace.runtime.models import RunRecord
from strategies.fixtures import build_gateway_fixture
from deeptrace.tools.evidence_store import EvidenceDraft
from datetime import UTC, datetime
from dataclasses import replace


class ProfileGateway:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def invoke(self, *, role, messages, **kwargs):
        self.calls.append((role, messages))
        if isinstance(self.response, BaseException):
            raise self.response
        return AIMessage(content=self.response)


class Strategy:
    def __init__(self, mode, evidence_id):
        self.mode = mode
        self.evidence_id = evidence_id
        self.calls = 0
        self.interrupt_once = False

    async def ainvoke(self, request, **kwargs):
        self.calls += 1
        if self.interrupt_once:
            self.interrupt_once = False
            raise asyncio.CancelledError()
        return {"outcome": ResearchOutcome(mode=self.mode, termination_reason="completed", executed_steps=1,
                                           evidence_ids=[self.evidence_id])}


class Answer:
    def __init__(self, evidence_id):
        self.evidence_id = evidence_id

    async def ainvoke(self, request, **kwargs):
        return {"outcome": ResponseOutcome(response_mode="answer", content="A complete research answer. [1]",
            citations=[{"evidence_id": self.evidence_id, "marker": "[1]"}], cited_evidence_ids=[self.evidence_id])}


async def setup(response, *, saver=None):
    gateway = ProfileGateway(response)
    fixture = build_gateway_fixture(model_gateway=gateway)
    evidence = await fixture.evidence_store.ingest(fixture.context.workspace_id, EvidenceDraft(
        canonical_url="https://example.com/source", title="Source", media_type="text/plain",
        body="A complete research answer.", fetched_at=datetime.now(UTC), source_quality=1.0))
    registry = StrategyRegistry()
    strategies = {mode: Strategy(mode, evidence.id) for mode in ResearchMode}
    for mode, strategy in strategies.items():
        registry.register(StrategyRegistration(mode, strategy))
    answers = ResponseGraphRegistry()
    answers.register(ResponseRegistration(ResponseMode.ANSWER, Answer(evidence.id)))
    graph = build_agent_runtime_graph(registry, answers, checkpointer=saver)
    return ResearchApplicationService(graph), fixture, gateway, strategies


def request(mode="auto", question="Research this task"):
    return ApplicationResearchRequest(run_id="route-run", thread_id="route-thread", question=question, mode=mode)


CONFIG = {"configurable": {"thread_id": "route-thread"}}


def test_new_requests_default_to_auto_and_preserve_manual_modes():
    assert ResearchRequest(question="Research this task").mode == "auto"
    assert ApplicationResearchRequest(run_id="r", thread_id="t", question="question").mode == "auto"
    assert ResearchRequest(question="q", mode="deep").mode == "plan_execute"
    assert ResearchRequest(question="q", mode=" AUTO ").mode == "auto"


@pytest.mark.asyncio
@pytest.mark.parametrize("profile,selected", [
    ({"dependent_steps": False, "independent_tracks": 1, "reason": "Focused documentation lookup"}, "workflow"),
    ({"dependent_steps": True, "independent_tracks": 3, "reason": "Later decisions depend on diagnosis"}, "plan_execute"),
    ({"dependent_steps": False, "independent_tracks": 3, "reason": "Clear scope but three independent investigations"}, "multi_agent"),
])
async def test_auto_routes_to_the_strategy_matching_task_characteristics(profile, selected):
    service, fixture, gateway, strategies = await setup(json.dumps(profile))
    result = await service.invoke(request(), config=CONFIG, context=fixture.context)
    assert result.research_outcome.mode.value == selected
    assert [mode.value for mode, strategy in strategies.items() if strategy.calls] == [selected]
    assert [role for role, _ in gateway.calls] == ["router"]
    routed = [payload for kind, payload in fixture.events.events if kind == "research.routed"]
    assert routed[0]["mode"] == selected
    assert routed[0]["reason"] == profile["reason"]


@pytest.mark.asyncio
async def test_manual_override_does_not_call_the_model_router():
    service, fixture, gateway, _ = await setup("not JSON")
    result = await service.invoke(request("multi_agent"), config=CONFIG, context=fixture.context)
    assert result.research_outcome.mode is ResearchMode.MULTI_AGENT
    assert gateway.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ["invalid JSON", '{"mode":"invented"}', RuntimeError("provider unavailable")])
async def test_bad_or_unavailable_classifier_falls_back_once_without_losing_the_task(response):
    service, fixture, gateway, _ = await setup(response)
    result = await service.invoke(request(), config=CONFIG, context=fixture.context)
    assert result.status == "completed"
    assert result.research_outcome.mode is ResearchMode.WORKFLOW
    assert len(gateway.calls) == 1
    routed = next(payload for kind, payload in fixture.events.events if kind == "research.routed")
    assert routed["action"] == "fallback"
    assert "provider unavailable" not in routed["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.CancelledError(), BudgetStateUnavailable()])
async def test_router_does_not_hide_cancellation_or_budget_store_failure(error):
    service, fixture, _, _ = await setup(error)
    with pytest.raises((type(error), NodeCancelledError)):
        await service.invoke(request(), config=CONFIG, context=fixture.context)


@pytest.mark.asyncio
async def test_non_research_memory_turn_does_not_route_or_call_the_classifier():
    service, fixture, gateway, strategies = await setup("invalid JSON")
    await service.invoke(request(question="请记住我偏好中文"), config=CONFIG, context=fixture.context)
    assert gateway.calls == []
    assert not any(strategy.calls for strategy in strategies.values())


@pytest.mark.asyncio
async def test_resume_uses_the_checkpointed_mode_without_reclassifying():
    saver = InMemorySaver(serde=create_harness_checkpoint_serializer())
    profile = {"dependent_steps": False, "independent_tracks": 3, "reason": "Independent tracks"}
    service, fixture, gateway, strategies = await setup(json.dumps(profile), saver=saver)
    strategies[ResearchMode.MULTI_AGENT].interrupt_once = True
    with pytest.raises((asyncio.CancelledError, NodeCancelledError)):
        await service.invoke(request(), config=CONFIG, context=fixture.context)
    gateway.response = "invalid JSON must not be read on resume"
    result = await service.invoke(request(), config=CONFIG, context=fixture.context)
    assert result.research_outcome.mode is ResearchMode.MULTI_AGENT
    assert len(gateway.calls) == 1


def test_public_run_keeps_request_selection_and_exposes_the_persisted_concrete_decision():
    record = RunRecord(id="r", question="q", mode="auto", created_at=datetime.now(UTC), events=[
        {"event_type": "research.routed", "details": {"mode": "multi_agent", "reason": "Independent tracks", "action": "automatic"}}
    ])
    reloaded = RunRecord.model_validate_json(record.model_dump_json())
    public = _record_to_response(reloaded)
    assert public["mode"] == "auto"
    assert public["selected_mode"] == "multi_agent"
    assert public["routing_reason"] == "Independent tracks"


@pytest.mark.asyncio
async def test_router_consumes_the_existing_shared_run_budget():
    from deeptrace.harness.model_budget import RunBudgetModelGateway, ModelBudgetExceeded
    from deeptrace.harness.prompts import task_messages

    profile = {"dependent_steps": False, "independent_tracks": 1, "reason": "Focused task"}
    service, fixture, provider, _ = await setup(json.dumps(profile))
    model = RunBudgetModelGateway(provider, max_calls=3)
    context = replace(fixture.context, model_gateway=model)
    await service.invoke(request(), config=CONFIG, context=context)
    assert model.used_calls == 1
    assert model.usage_payload()["provider_attempts"] == 1
    with pytest.raises(ModelBudgetExceeded):
        await model.invoke(role="researcher", messages=task_messages(instruction="instruction", task="task"))
    assert len(provider.calls) == 1
