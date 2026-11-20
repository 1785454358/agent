import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResponseMode
from deeptrace.harness.token_budget import TokenBudgetConfig
from deeptrace.responses.graph import (
    build_answer_graph,
    build_brief_graph,
    build_report_graph,
)
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from responses.test_graph import _response_input, _seed_evidence
from responses.test_supported_findings import _case


class Reviewer:
    def __init__(self, reviewed="## 结论\n\n结果仅在限定条件下成立 [1]。"):
        self.calls = []
        self.reviewed = reviewed

    async def invoke(self, *, role, messages, tools=None):
        prompt = "\n".join(str(m.content) for m in messages)
        self.calls.append(prompt)
        if "ANSWER_REVIEW_JSON:" in prompt:
            return AIMessage(content=json.dumps({
                "content": self.reviewed, "issues": ["保留限定条件"], "unanswered_points": [],
            }))
        return AIMessage(content=json.dumps({"content": "结果在所有条件下必然成立 [1]。"}))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,builder", [
    (ResponseMode.ANSWER, build_answer_graph),
    (ResponseMode.BRIEF, build_brief_graph),
    (ResponseMode.REPORT, build_report_graph),
])
async def test_every_response_form_reviews_unsupported_generalizations(mode, builder):
    payload, _, fixture, _ = await _case()
    payload.response_mode = mode
    model = Reviewer()
    result = await builder().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=True,
    ))
    assert len(model.calls) == 2
    assert result["outcome"].content == model.reviewed
    assert result["outcome"].response_mode == mode
    assert result["outcome"].partial_reason is None


@pytest.mark.asyncio
async def test_long_report_review_preserves_report_instead_of_forcing_8000_chars():
    payload, _, fixture, _ = await _case()
    payload.response_mode = ResponseMode.REPORT
    model = Reviewer("## 分节报告\n\n" + "受原文限定条件约束的结论 [1]。\n\n" * 450)
    result = await build_report_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=True,
    ))
    assert len(model.reviewed) > 8000
    assert result["outcome"].content == model.reviewed.strip()
    assert len(model.calls) == 2
    assert "不超过50000字符" in model.calls[1]


@pytest.mark.asyncio
async def test_follow_up_without_research_outcome_uses_only_writer_visible_text():
    store = InMemoryEvidenceStore()
    body = "事实材料。" * 900 + "HIDDEN_TAIL_CONDITION."
    ids = await _seed_evidence(store, [("https://example.com/a", "Source", body)])
    model = Reviewer()
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    payload = _response_input(ids, question="解释已有材料")
    payload.research_outcome = None
    result = await build_answer_graph(TokenBudgetConfig(
        context_tokens=7000, output_reserve_tokens=0, safety_tokens=0,
    )).ainvoke({"response_input": payload}, context=replace(
        fixture.context, response_fact_review=True,
    ))
    assert len(model.calls) == 2
    assert "HIDDEN_TAIL_CONDITION" not in model.calls[0]
    review = json.loads(model.calls[1].split("ANSWER_REVIEW_JSON:\n", 1)[1])
    assert review["original_passages"]
    assert all(block in model.calls[0] for block in review["original_passages"])
    assert "HIDDEN_TAIL_CONDITION" not in model.calls[1]
    assert result["outcome"].partial_reason is None


@pytest.mark.asyncio
async def test_review_rejects_raw_control_characters():
    payload, _, fixture, _ = await _case()
    model = Reviewer("合法引用 [1]。\x00恶意控制字符")
    result = await build_answer_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=True,
    ))
    assert "\x00" not in result["outcome"].content
    assert result["outcome"].partial_reason == "answer_review_unavailable"


@pytest.mark.asyncio
async def test_review_budget_exhaustion_preserves_cited_draft_as_explicit_partial():
    from deeptrace.harness.model_budget import ModelBudgetExceeded

    class ExhaustedReviewer(Reviewer):
        async def invoke(self, *, role, messages, tools=None):
            if "ANSWER_REVIEW_JSON:" in str(messages):
                raise ModelBudgetExceeded("input_tokens")
            return await super().invoke(role=role, messages=messages, tools=tools)

    payload, _, fixture, _ = await _case()
    result = await build_answer_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=ExhaustedReviewer(), response_fact_review=True,
    ))
    outcome = result["outcome"]
    assert "结果在所有条件下必然成立 [1]" in outcome.content
    assert "未经最终事实审查" in outcome.content
    assert outcome.partial_reason == "answer_review_unavailable"


@pytest.mark.asyncio
async def test_large_output_cap_does_not_consume_remaining_run_input_twice():
    class RemainingReviewer(Reviewer):
        async def available_input_tokens(self, role):
            return 18000

    payload, _, fixture, _ = await _case()
    model = RemainingReviewer()
    result = await build_answer_graph(TokenBudgetConfig(
        context_tokens=256000, output_reserve_tokens=16000, safety_tokens=4096,
    )).ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=True,
    ))
    assert len(model.calls) == 2
    assert result["outcome"].content == model.reviewed


@pytest.mark.asyncio
async def test_run_limited_writer_keeps_verified_support_before_optional_page_text():
    class RemainingReviewer(Reviewer):
        async def available_input_tokens(self, role):
            return 5000

    payload, _, fixture, _ = await _case()
    model = RemainingReviewer()
    result = await build_answer_graph().ainvoke({"response_input": payload}, context=replace(
        fixture.context, model_gateway=model, response_fact_review=True,
    ))
    assert len(model.calls) == 2
    assert "Rare supported qualifier." in model.calls[0]
    assert result["outcome"].content == model.reviewed
    assert result["outcome"].partial_reason is None


@pytest.mark.asyncio
async def test_review_context_admission_failure_keeps_substantive_draft_with_warning():
    class ContextLimitedReviewer(Reviewer):
        checks = 0
        async def available_input_tokens(self, role):
            self.checks += 1
            return 18000 if self.checks == 1 else 1
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({'content': '这是保留限定条件的实质回答 [1]。'}))

    payload, _, fixture, _ = await _case()
    result = await build_answer_graph().ainvoke({'response_input': payload}, context=replace(
        fixture.context, model_gateway=ContextLimitedReviewer(), response_fact_review=True,
    ))
    assert '这是保留限定条件的实质回答' in result['outcome'].content
    assert '未经最终事实审查' in result['outcome'].content
    assert result['outcome'].partial_reason == 'answer_review_unavailable'
