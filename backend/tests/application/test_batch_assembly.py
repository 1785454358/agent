import json
from dataclasses import replace

import pytest
from harness.test_batch_research import BatchModel
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture, evaluation_payload_from_view

from deeptrace.application import assembly
from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings


class ResearchModel(BatchModel):
    async def invoke(self, *, role, messages, tools=None):
        if role == "researcher":
            return await super().invoke(role=role, messages=messages, tools=tools)
        self.calls.append((role, messages, tools))
        if role in {"planner", "supervisor"}:
            return AIMessage(content=json.dumps({"queries": ["topic-one", "topic-two"],
                "requirements": [{"id": "r1", "description": "topic 的事实"}],
                "query_targets": {"topic-one": ["r1"], "topic-two": ["r1"]},
                "task_briefs": {q:{"read_terms":["topic fact"]} for q in ["topic-one","topic-two"]}}))
        if role == "coverage_reviewer":
            return AIMessage(content=json.dumps({"covered_requirement_ids": ["r1"], "tasks": []}))
        if role == "evaluator":
            prompt = str(messages[-1].content)
            payload = evaluation_payload_from_view(prompt)
            material = json.JSONDecoder().raw_decode(
                prompt.rsplit("\nEVIDENCE_VIEW_JSON:\n", 1)[1]
            )[0]
            findings = [
                {
                    "id": f"finding-{index}",
                    "claim": passage["text"][:500],
                    "confidence": 0.9,
                    "supports": [{"ref": passage["ref"]}],
                }
                for index, passage in enumerate(material["passages"], 1)
            ]
            if findings:
                payload["findings"] = findings
                for item in payload["coverage"]["items"]:
                    item.update(
                        status="covered",
                        reason="verified source-backed fact",
                        finding_ids=[finding["id"] for finding in findings],
                    )
            return AIMessage(content=json.dumps(payload))
        if role == "responder":
            if "ANSWER_REVIEW_JSON:" in str(messages[-1].content):
                return AIMessage(content=json.dumps({"content": "原文记录了 topic 的两个事实：one 和 two。[1][2]",
                    "unanswered_points": []}))
            return AIMessage(content=json.dumps({"content": "原文记录了 topic 的两个事实：one 和 two。[1][2]"}))
        raise AssertionError(role)


@pytest.mark.asyncio
@pytest.mark.parametrize('model,mode,expected', [
    ('doubao-seed-2.0-lite', 'auto', {'thinking': {'type': 'disabled'}}),
    ('doubao-seed-2-0-lite-260428', 'auto', {'thinking': {'type': 'disabled'}}),
    ('generic-chat-model', 'auto', None),
    ('doubao-seed-2.0-pro', 'auto', None),
    ('doubao-seed-2.0-lite', 'provider_default', None),
    ('doubao-seed-2.0-lite', 'enabled', {'thinking': {'type': 'enabled'}}),
])
async def test_production_provider_payload_respects_thinking_mode(tmp_path, model, mode, expected):
    from langchain_core.messages import HumanMessage
    settings = Settings('test', 'https://example.com/v1', model, 'test',
                        memory_retrieval='lexical', model_thinking=mode)
    bundle = assembly.build_harness_runtime(settings, runs_dir=tmp_path)
    try:
        provider = bundle.context_factory('run-1').model_gateway.inner._model
        payload = provider._get_request_payload([HumanMessage(content='test')])
        assert payload.get('extra_body') == expected
    finally:
        await bundle.aclose()


@pytest.mark.asyncio
async def test_legacy_config_alias_uses_delivery_first_collection(tmp_path, monkeypatch):
    model = ResearchModel()
    monkeypatch.setattr(assembly, "ChatModelGateway", lambda *args, **kwargs: model)
    # ResearchModel scripts the legacy plan_execute action schema. Keep this
    # compatibility test explicit; controller production tests use sufficient.
    settings = Settings("test", "https://example.com/v1", "test", "test",
                        memory_retrieval="lexical", research_orchestrator="legacy")
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
        assert [r for r, _, _ in model.calls] == ["planner", "coverage_reviewer", "responder"]
        assert result.research_outcome.delivery_first
        assert result.research_outcome.read_anchors
        assert result.research_outcome.coverage is None
        assert context.response_fact_review
        event_types = [kind for kind, _ in fixture.events.events]
        phases = ["run.started", "planning.started", "planning.completed", "research.coverage.reviewed",
                  "writing.started", "writing.completed"]
        assert all(kind in event_types for kind in phases)
        assert [event_types.index(kind) for kind in phases] == sorted(event_types.index(kind) for kind in phases)
        assert "evaluation.started" not in event_types
        plan_event = next(payload for kind, payload in fixture.events.events if kind == "planning.completed")
        assert len(json.loads(plan_event["tasks_json"])) == 2
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


@pytest.mark.asyncio
async def test_completed_run_resources_can_be_released_without_resetting_budget(tmp_path, monkeypatch):
    from harness.test_durable_model_budget import Provider, call
    model = Provider()
    monkeypatch.setattr(assembly, 'ChatModelGateway', lambda *args, **kwargs: model)
    settings = Settings('test', 'https://example.com/v1', 'test', 'test',
                        memory_retrieval='lexical', max_model_calls=3,
                        response_fact_review=False)
    bundle = assembly.build_harness_runtime(settings, runs_dir=tmp_path)
    try:
        first = bundle.context_factory('run-1').model_gateway
        await call(first)
        bundle.release_run('run-1')
        second = bundle.context_factory('run-1').model_gateway
        assert second is not first
        with pytest.raises(RuntimeError, match='budget_exhausted:model_calls'):
            await call(second)
        assert second.usage_payload()['input_tokens'] == 70
        assert model.calls == 1
    finally:
        await bundle.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("model,enabled", [
    ("doubao-seed-2.0-lite", True),
    ("doubao-seed-2-0-lite-260428", True),
    ("deepseek-v4.1-flash", True),
    ("deepseek-v4-1-flash-260910", True),
    ("generic-chat-model", False),
])
async def test_known_json_provider_serializes_structured_roles_without_changing_tools(
    tmp_path, model, enabled,
):
    from langchain_core.messages import HumanMessage

    settings = Settings("test", "https://example.com/v1", model, "test", memory_retrieval="lexical")
    bundle = assembly.build_harness_runtime(settings, runs_dir=tmp_path)
    try:
        gateway = bundle.context_factory("run-1").model_gateway.inner
        for role in ("planner", "replanner", "supervisor", "follow_up", "evaluator", "responder"):
            options = gateway._role_overrides.get(role, {})
            payload = gateway._model._get_request_payload(
                [HumanMessage(content='Return JSON {"content":"quoted words"}')],
                **options,
            )
            assert payload.get("response_format") == ({"type": "json_object"} if enabled else None)
        assert "response_format" not in gateway._role_overrides.get("researcher", {})
    finally:
        await bundle.aclose()
