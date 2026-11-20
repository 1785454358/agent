import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture

from deeptrace.responses.graph import build_answer_graph
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from responses.test_graph import ScriptedModelGateway, _response_input, _seed_evidence


@pytest.mark.asyncio
async def test_detailed_question_gets_room_for_explanation_and_markdown():
    content = (
        "## 结论\n\n**适用条件**如下 [1]。\n\n" + "有条件的机制解释 [1]。\n\n" * 150
    )
    model = ScriptedModelGateway({"responder": json.dumps({"content": content})})
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "Source", "Original facts.")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    payload = _response_input(
        ids, question="请详细比较两种实现，解释机制、适用条件并给示例"
    )
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=fixture.context
    )
    assert result["outcome"].content == content.strip()
    assert len(model.calls) == 1
    assert "禁止使用 Markdown" not in model.calls[0][1]
    assert "结论" in model.calls[0][1] and "取舍" in model.calls[0][1]


@pytest.mark.asyncio
async def test_simple_question_stays_bounded_and_explicit_cap_still_wins():
    model = ScriptedModelGateway({"responder": json.dumps({"content": "结论 [1]。"})})
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "Source", "Original facts.")]
    )
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    for question, cap in [("What is X?", None), ("请详细比较机制", 600)]:
        context = replace(fixture.context, response_max_content_chars=cap)
        await build_answer_graph().ainvoke(
            {"response_input": _response_input(ids, question=question)},
            context=context,
        )
        assert f"全文不超过 {cap or 2000} 个字符" in model.calls[-1][1]


@pytest.mark.asyncio
async def test_review_preserves_complex_answer_length_and_repairs_from_same_sources():
    from responses.test_supported_findings import _case

    payload, _, fixture, _ = await _case()
    payload.question = "详细解释该结论的机制和适用条件，并给出示例"
    long_content = "## 结论\n\n" + "受 Rare supported qualifier. 限制 [1]。\n\n" * 70

    class Model:
        def __init__(self):
            self.prompts = []

        async def invoke(self, *, role, messages, tools=None):
            prompt = "\n".join(str(m.content) for m in messages)
            self.prompts.append(prompt)
            if "ANSWER_REVIEW_JSON:" in prompt:
                assert "Rare supported qualifier." in prompt
                assert '"answer_requirements"' in prompt
                assert payload.research_outcome.requirements[0].description in prompt
                return AIMessage(
                    content=json.dumps(
                        {
                            "content": long_content,
                            "issues": [],
                            "unanswered_points": [],
                        }
                    )
                )
            return AIMessage(content=json.dumps({"content": long_content}))

    model = Model()
    context = replace(fixture.context, model_gateway=model, response_fact_review=True)
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=context
    )
    assert len(long_content) > 2000
    assert result["outcome"].content == long_content.strip()
    assert result["outcome"].partial_reason is None
    assert "已支持" in model.prompts[-1]


def test_custom_policy_length_is_an_explicit_ceiling():
    from deeptrace.responses.writing import ANSWER_POLICY, effective_policy

    payload = _response_input([], question="请详细解释")
    policy = replace(ANSWER_POLICY, max_content_chars=700)
    assert (
        effective_policy(
            policy, build_gateway_fixture().context, payload
        ).max_content_chars
        == 700
    )


def test_length_policy_counts_research_requirements_without_inventing_new_ones():
    from deeptrace.domain import ResearchRequirement
    from deeptrace.responses.writing import ANSWER_POLICY, effective_policy

    payload = _response_input([], question="Explain X")
    payload.research_outcome.requirements = [
        ResearchRequirement(id=f"r{i}", description=f"point {i}") for i in range(1, 7)
    ]
    fixture = build_gateway_fixture()
    assert (
        effective_policy(ANSWER_POLICY, fixture.context, payload).max_content_chars
        == 8000
    )


@pytest.mark.asyncio
async def test_mixed_valid_and_unknown_review_citations_do_not_publish_unsupported_claim():
    from responses.test_fact_review import ReviewingModel
    from responses.test_supported_findings import _case

    payload, _, fixture, _ = await _case()
    model = ReviewingModel(
        json.dumps(
            {
                "content": "Rare supported qualifier. [1]。编造的新结论 [99]。",
                "issues": [],
                "unanswered_points": [],
            }
        )
    )
    context = replace(fixture.context, model_gateway=model, response_fact_review=True)
    result = await build_answer_graph().ainvoke(
        {"response_input": payload}, context=context
    )
    assert "编造的新结论" not in result["outcome"].content
    assert result["outcome"].partial_reason is not None
