"""Catch unconstrained first drafts that exhaust a small response budget."""

import json
import re
from types import SimpleNamespace

import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResponseMode
from deeptrace.responses.graph import build_report_graph
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from responses.test_graph import ScriptedModelGateway, _response_input, _seed_evidence


def length_sensitive_response(prompt):
    bounds = re.findall(r"全文不超过 (\d+) 个字符", prompt)
    if not bounds or min(map(int, bounds)) > 600:
        return '{"content": "长报告在输出上限处截断'
    return json.dumps({"content": "图状态由检查点保存，跨线程使用 Store [1]。"})


@pytest.mark.asyncio
async def test_small_response_cap_reaches_initial_draft_and_produces_complete_report():
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store,
        [("https://example.com/a", "source", "图状态由检查点保存，跨线程使用 Store。")],
    )
    model = ScriptedModelGateway({"responder": length_sensitive_response})
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    context = SimpleNamespace(
        **{**vars(fixture.context), "response_max_content_chars": 600}
    )
    result = await build_report_graph().ainvoke(
        {"response_input": _response_input(ids, mode=ResponseMode.REPORT)},
        context=context,
    )
    outcome = result["outcome"]
    assert outcome.partial_reason is None
    assert outcome.content == "图状态由检查点保存，跨线程使用 Store [1]。"
    assert outcome.cited_evidence_ids == ids
    assert len(model.calls) == 1  # repair is not needed when first draft is bounded


@pytest.mark.asyncio
async def test_correction_and_validation_keep_same_explicit_length_cap():
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(store, [("https://example.com/a", "source", "fact")])
    replies = iter(
        ['{"content": "broken', json.dumps({"content": "可靠结论 [1]。" * 70})]
    )
    model = ScriptedModelGateway({"responder": lambda prompt: next(replies)})
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    context = SimpleNamespace(
        **{**vars(fixture.context), "response_max_content_chars": 600}
    )
    result = await build_report_graph().ainvoke(
        {"response_input": _response_input(ids, mode=ResponseMode.REPORT)},
        context=context,
    )
    assert len(result["outcome"].content) <= 600
    assert result["outcome"].content.endswith("。")
    assert result["outcome"].cited_evidence_ids == ids
