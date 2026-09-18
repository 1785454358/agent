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


def test_strip_markdown_headings_keeps_non_heading_hashes() -> None:
    from deeptrace.responses.graph import strip_markdown_headings

    text = "## 标题\nC# 是语言\n编号 #1 保留\n**加粗**文字"
    assert strip_markdown_headings(text) == "标题\nC# 是语言\n编号 #1 保留\n加粗文字"


@pytest.mark.asyncio
async def test_report_markdown_headings_are_stripped_to_plain_text() -> None:
    model = ScriptedModelGateway(
        {
            "responder": json.dumps(
                {
                    "content": (
                        "# 2026 年报告\n\n"
                        "## 一、概述\n"
                        "结论一 [1]。\n\n"
                        "### （一）子节\n"
                        "**重点**：结论二 [1]。"
                    )
                }
            )
        }
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    result = await _run_response(
        build_report_graph(),
        model,
        _response_input(ids, mode=ResponseMode.REPORT),
        fixture,
    )
    outcome = result["outcome"]

    assert "#" not in outcome.content
    assert "**" not in outcome.content
    assert "一、概述" in outcome.content
    assert "重点：结论二 [1]。" in outcome.content
    # the prompt itself also forbids markdown so the model is nudged up front
    assert "禁止使用 Markdown" in model.calls[0][1]


@pytest.mark.asyncio
async def test_response_budget_reserves_output_and_reports_trimming() -> None:
    from deeptrace.harness.token_budget import TokenBudgetConfig

    model = ScriptedModelGateway(
        {"responder": json.dumps({"content": "结论 [1]。"})}
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/big", "Big", "word " * 2000)]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    # a tiny input budget must trim elastic evidence but keep pinned blocks
    config = TokenBudgetConfig(
        context_tokens=800, output_reserve_tokens=600, safety_tokens=0
    )

    result = await _run_response(
        build_answer_graph(config), model, _response_input(ids), fixture
    )

    prompt = model.calls[0][1]
    assert "只输出 JSON" in prompt
    assert "用户问题" in prompt
    assert result["outcome"].content == "结论 [1]。"
    assert any(
        event_type == "response.budget"
        for event_type, _payload in fixture.events.events
    )


def test_incomplete_and_sentence_cut_helpers() -> None:
    from deeptrace.responses.graph import _cut_at_sentence, _looks_incomplete

    assert _looks_incomplete("这是一个没有结尾的句子 [1]，")
    assert _looks_incomplete("列举如下：")
    assert not _looks_incomplete("结论已经给出 [1]。")
    assert not _looks_incomplete("结论已经给出 [1]")

    text = "第一句。" * 300
    cut = _cut_at_sentence(text, 50)
    assert len(cut) <= 50
    assert cut.endswith("。")


@pytest.mark.asyncio
async def test_over_length_output_is_rewritten_within_the_cap() -> None:
    long_body = "这是一段很长的正文内容 [1]。" * 400

    def responder(prompt: str) -> str:
        if "超过篇幅上限" in prompt:
            return json.dumps({"content": "精简后的完整回答 [1]。"})
        return json.dumps({"content": long_body})

    model = ScriptedModelGateway({"responder": responder})
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    result = await _run_response(
        build_answer_graph(), model, _response_input(ids), fixture
    )

    assert result["outcome"].content == "精简后的完整回答 [1]。"
    assert not any(
        event_type == "response.truncated"
        for event_type, _payload in fixture.events.events
    )


@pytest.mark.asyncio
async def test_output_that_stays_too_long_is_cut_at_a_sentence_and_flagged() -> None:
    model = ScriptedModelGateway(
        {"responder": json.dumps({"content": "一段过长的正文内容 [1]。" * 400})}
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    result = await _run_response(
        build_answer_graph(), model, _response_input(ids), fixture
    )
    content = result["outcome"].content

    assert len(content) <= 2000
    assert content.endswith("。")
    details = [
        payload
        for event_type, payload in fixture.events.events
        if event_type == "response.truncated"
    ]
    assert details and details[0]["output_truncated"] is True


@pytest.mark.asyncio
async def test_dangling_output_triggers_one_completion_retry() -> None:
    def responder(prompt: str) -> str:
        if "不完整" in prompt:
            return json.dumps({"content": "补全后的回答 [1]。"})
        return json.dumps({"content": "这是一个没有结尾的句子 [1]，"})

    model = ScriptedModelGateway({"responder": responder})
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    result = await _run_response(
        build_answer_graph(), model, _response_input(ids), fixture
    )

    assert result["outcome"].content == "补全后的回答 [1]。"
    assert len(model.calls) == 2


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
async def test_zero_marker_first_draft_triggers_one_corrective_retry() -> None:
    def responder(prompt: str) -> str:
        if "上一版输出未通过校验" in prompt:
            return json.dumps({"content": "纠正后的结论 [1]。"})
        return json.dumps({"content": "没有任何角标的初稿。"})

    model = ScriptedModelGateway({"responder": responder})
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "来源 A", "unique-body-a")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)

    result = await _run_response(
        build_answer_graph(), model, _response_input(ids), fixture
    )
    outcome = result["outcome"]

    assert len(model.calls) == 2
    assert outcome.partial_reason is None
    assert outcome.content == "纠正后的结论 [1]。"
    assert outcome.citations[0].evidence_id == ids[0]


@pytest.mark.asyncio
async def test_prose_wrapped_json_envelope_is_recovered() -> None:
    model = ScriptedModelGateway(
        {"responder": '结果如下：{"content": "包裹在散文里的结论 [1]。"}以上。'}
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

    assert len(model.calls) == 1
    assert outcome.partial_reason is None
    assert outcome.content == "包裹在散文里的结论 [1]。"


@pytest.mark.asyncio
async def test_persistent_markerless_draft_still_falls_back() -> None:
    model = ScriptedModelGateway(
        {"responder": json.dumps({"content": "始终不带角标的内容。"})}
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

    assert len(model.calls) == 2
    assert outcome.partial_reason == "no_supported_citations"
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
