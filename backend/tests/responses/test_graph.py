from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import (
    EvidenceLifecycleStatus,
    ResearchMode,
    ResearchOutcome,
    ResponseInput,
    ResponseMode,
)
from deeptrace.responses.graph import (
    build_answer_graph,
    build_brief_graph,
    build_report_graph,
)
from deeptrace.tools.evidence_store import EvidenceDraft, InMemoryEvidenceStore

from strategies.fixtures import TENANT_ID, build_gateway_fixture


class ScriptedModelGateway:
    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    async def invoke(self, *, role: str, messages: list[Any]) -> Any:
        prompt = str(messages[-1].content)
        self.calls.append((role, prompt))
        response = self._responses[role]
        if callable(response):
            response = response(prompt)
        if isinstance(response, Exception):
            raise response
        return response


async def _seed_evidence(
    store: InMemoryEvidenceStore,
    entries: list[tuple[str, str, str]],
) -> list[str]:
    ids = []
    for url, title, body in entries:
        evidence = await store.ingest(
            TENANT_ID,
            EvidenceDraft(
                canonical_url=url,
                title=title,
                media_type="text/html",
                body=body,
                fetched_at=datetime(2026, 9, 12, tzinfo=UTC),
                source_quality=0.9,
            ),
        )
        ids.append(evidence.id)
    return ids


def _response_input(
    evidence_ids: list[str],
    *,
    mode: ResponseMode = ResponseMode.ANSWER,
    question: str = "总结研究结论",
) -> ResponseInput:
    return ResponseInput(
        question=question,
        response_mode=mode,
        research_outcome=ResearchOutcome(
            mode=ResearchMode.WORKFLOW,
            evidence_ids=list(evidence_ids),
            findings=[],
            unresolved_gaps=[],
            executed_steps=2,
            termination_reason="completed",
        ),
        active_evidence_ids=list(evidence_ids),
    )


async def _run_response(graph, model: ScriptedModelGateway, payload, fixture):
    result = await graph.ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    return result


@pytest.mark.asyncio
async def test_answer_graph_is_concise_and_cites_loaded_evidence() -> None:
    model = ScriptedModelGateway(
        {"responder": json.dumps({"content": "结论是 Harness 已统一 [1]。"})}
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store,
        [("https://example.com/a", "来源 A", "unique-body-a")],
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    graph = build_answer_graph()
    result = await _run_response(
        graph, model, _response_input(ids), fixture
    )
    outcome = result["outcome"]

    assert [role for role, _ in model.calls] == ["responder"]
    assert "简洁" in model.calls[0][1]
    assert outcome.response_mode is ResponseMode.ANSWER
    assert outcome.partial_reason is None
    assert outcome.citations[0].evidence_id == ids[0]
    assert outcome.citations[0].marker == "[1]"
    assert outcome.content == "结论是 Harness 已统一 [1]。"


@pytest.mark.asyncio
async def test_brief_and_report_prompts_differ_by_policy() -> None:
    model = ScriptedModelGateway(
        {"responder": json.dumps({"content": "结构化输出 [1]"})}
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    for builder, expected_mode, expected_fragment in (
        (build_brief_graph, ResponseMode.BRIEF, "结构化"),
        (build_report_graph, ResponseMode.REPORT, "正式报告"),
    ):
        model.calls.clear()
        graph = builder()
        result = await _run_response(
            graph,
            model,
            _response_input(ids, mode=expected_mode),
            fixture,
        )
        assert expected_fragment in model.calls[0][1]
        assert result["outcome"].response_mode is expected_mode


@pytest.mark.asyncio
async def test_unknown_citation_markers_are_dropped_never_invented() -> None:
    model = ScriptedModelGateway(
        {
            "responder": json.dumps(
                {"content": "有依据的部分 [1]，幻觉部分 [3]。"}
            )
        }
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    result = await _run_response(
        build_answer_graph(), model, _response_input(ids), fixture
    )
    outcome = result["outcome"]

    assert [citation.evidence_id for citation in outcome.citations] == [ids[0]]
    assert "[3]" not in outcome.content
    assert "幻觉部分" in outcome.content


@pytest.mark.asyncio
async def test_generation_failure_returns_evidence_backed_partial() -> None:
    model = ScriptedModelGateway({"responder": "完全不是 JSON"})
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    result = await _run_response(
        build_answer_graph(), model, _response_input(ids), fixture
    )
    outcome = result["outcome"]

    assert outcome.partial_reason == "generation_failed"
    assert ids[0] in outcome.cited_evidence_ids
    assert "来源 A" in outcome.content


@pytest.mark.asyncio
async def test_cross_tenant_evidence_ids_are_never_loadable() -> None:
    model = ScriptedModelGateway(
        {"responder": json.dumps({"content": "回答 [1]"})}
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    payload = _response_input(["evidence-foreign-tenant", ids[0]])
    result = await _run_response(build_answer_graph(), model, payload, fixture)
    outcome = result["outcome"]

    assert outcome.citations[0].evidence_id == ids[0]
    assert "evidence-foreign-tenant" not in outcome.cited_evidence_ids
    assert model.calls[0][1].count("[") >= 1


@pytest.mark.asyncio
async def test_no_usable_evidence_yields_partial_without_model_call() -> None:
    model = ScriptedModelGateway({"responder": "must not run"})
    fixture = build_gateway_fixture(model_gateway=model)

    payload = _response_input([])
    result = await _run_response(build_answer_graph(), model, payload, fixture)
    outcome = result["outcome"]

    assert model.calls == []
    assert outcome.partial_reason == "no_evidence"
    assert outcome.citations == []


@pytest.mark.asyncio
async def test_response_state_never_contains_evidence_bodies() -> None:
    model = ScriptedModelGateway(
        {"responder": json.dumps({"content": "结论 [1]"})}
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-private-body-marker")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    checkpointer = InMemorySaver()
    graph = build_answer_graph(checkpointer=checkpointer)

    result = await graph.ainvoke(
        {"response_input": _response_input(ids)},
        config={"configurable": {"thread_id": "response-thread"}},
        context=fixture.context,
    )

    assert result["outcome"].partial_reason is None
    snapshot = await build_answer_graph(checkpointer=checkpointer).aget_state(
        {"configurable": {"thread_id": "response-thread"}}
    )
    serialized = json.dumps(snapshot.values, default=str, ensure_ascii=False)
    assert "unique-private-body-marker" not in serialized
