"""Final delivery must follow the user, rather than generated research scope."""

import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from deeptrace.domain import ResponseMode
from deeptrace.harness.model_budget import ModelBudgetExceeded
from deeptrace.responses.fact_review import review_answer, review_messages
from deeptrace.responses.graph import build_answer_graph, build_report_graph
from responses.test_supported_findings import _case


def review_payload(mode):
    messages = review_messages(
        question="State both conditions.", constraints=["Only supplied evidence"],
        content="A draft [1].", sources=["[1] A and B are required."],
        requirements=["Provide an unasked migration tutorial"], response_mode=mode)
    data = json.loads(messages[-1].content.split("ANSWER_REVIEW_JSON:\n", 1)[1])
    return messages, data


def test_answer_review_does_not_promote_a_planner_addition_to_a_user_requirement():
    messages, data = review_payload(ResponseMode.ANSWER)
    assert data["answer_requirements"] == []
    assert data["draft"] == ""
    assert "A draft [1]." not in "\n".join(m.content for m in messages)
    assert data["original_passages"] == ["[1] A and B are required."]
    assert data["user_request"] == {"question": "State both conditions.",
                                    "constraints": ["Only supplied evidence"]}
    assert list(data)[-1] == "user_request"
    assert "State both conditions." in messages[-1].content
    assert "Only supplied evidence" in messages[-1].content


@pytest.mark.parametrize("mode", [ResponseMode.REPORT, ResponseMode.BRIEF, None])
def test_non_answer_review_preserves_the_existing_research_checklist(mode):
    _, data = review_payload(mode)
    assert data["answer_requirements"] == ["Provide an unasked migration tutorial"]
    assert data["draft"] == "A draft [1]."


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ResponseMode.ANSWER, ResponseMode.REPORT])
async def test_response_graph_passes_the_actual_delivery_mode_to_review(mode):
    payload, _, fixture, _ = await _case()
    payload.response_mode = mode
    delivered = []

    class Model:
        async def invoke(self, *, messages, **kwargs):
            text = messages[-1].content
            if "ANSWER_REVIEW_JSON:\n" in text:
                delivered.append(json.loads(text.split("ANSWER_REVIEW_JSON:\n", 1)[1]))
                return AIMessage(content=json.dumps({
                    "content": "受 Rare supported qualifier. 限制 [1]。",
                    "issues": [], "unanswered_points": []}))
            return AIMessage(content=json.dumps({"content": "受 Rare supported qualifier. 限制 [1]。"}))

    context = replace(fixture.context, model_gateway=Model(), response_fact_review=True)
    graph = build_answer_graph() if mode is ResponseMode.ANSWER else build_report_graph()
    result = await graph.ainvoke({"response_input": payload}, context=context)
    expected = [] if mode is ResponseMode.ANSWER else [
        r.description for r in payload.research_outcome.requirements]
    assert delivered[0]["answer_requirements"] == expected
    assert "Rare supported qualifier." in "\n".join(delivered[0]["original_passages"])
    assert result["outcome"].partial_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ResponseMode.ANSWER, ResponseMode.REPORT, None])
async def test_answer_gap_must_be_traceable_to_a_user_request(mode):
    _, _, fixture, _ = await _case()

    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({
                "content": "Only A is established [1].", "issues": [],
                "unanswered_points": ["Provide an unasked migration tutorial"]}))

    context = replace(fixture.context, model_gateway=Model())
    args = dict(question="State A and B.", constraints=[], content="A [1].",
                sources=["[1] A."], input_budget=8000, response_mode=mode)
    if mode is ResponseMode.ANSWER:
        with pytest.raises(ValueError, match="answer_gap_not_in_user_request"):
            await review_answer(context, **args)
    else:
        reviewed = await review_answer(context, **args)
        assert reviewed.unanswered_points == ["Provide an unasked migration tutorial"]


@pytest.mark.asyncio
@pytest.mark.parametrize("gap", ["B", "Include the unit"])
async def test_actual_missing_user_point_is_retained(gap):
    _, _, fixture, _ = await _case()

    class Model:
        async def invoke(self, **kwargs):
            return AIMessage(content=json.dumps({
                "content": "Only A is established [1].", "issues": [],
                "unanswered_points": [gap]}))

    reviewed = await review_answer(
        replace(fixture.context, model_gateway=Model()), question="State A and B.",
        constraints=["Include the unit"], content="A [1].", sources=["[1] A."],
        input_budget=8000, response_mode=ResponseMode.ANSWER)
    assert reviewed.unanswered_points == [gap]


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", ["valid", "invalid", "budget"])
async def test_citation_protocol_has_one_bounded_repair_with_the_same_sources(repair):
    _, _, fixture, _ = await _case()

    class Model:
        def __init__(self):
            self.calls = []

        async def invoke(self, *, messages, **kwargs):
            self.calls.append(messages)
            if len(self.calls) == 2 and repair == "budget":
                raise ModelBudgetExceeded("model_calls")
            citation = "[1]" if len(self.calls) == 2 and repair == "valid" else "[99]"
            return AIMessage(content=json.dumps({
                "content": f"A {citation}.", "issues": [], "unanswered_points": []}))

    model = Model()
    args = dict(question="State A.", constraints=[], content="An unrelated draft.",
                sources=["[1] A."], input_budget=8000, response_mode=ResponseMode.ANSWER)
    context = replace(fixture.context, model_gateway=model)
    if repair == "valid":
        reviewed = await review_answer(context, **args)
        assert reviewed.content == "A [1]."
    elif repair == "budget":
        with pytest.raises(ModelBudgetExceeded):
            await review_answer(context, **args)
    else:
        with pytest.raises(ValueError, match="invalid_reviewed_citation"):
            await review_answer(context, **args)
    assert len(model.calls) == 2
    for messages in model.calls:
        data = json.loads(messages[-1].content.split("ANSWER_REVIEW_JSON:\n", 1)[1])
        assert data["original_passages"] == ["[1] A."]
        assert data["draft"] == ""
        assert data["user_request"]["question"] == "State A."
