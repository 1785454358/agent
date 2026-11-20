"""Repair only invalid citation syntax, through the same budgeted gateway."""

import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage

from deeptrace.harness.model_budget import ModelBudgetExceeded
from deeptrace.responses.fact_review import review_answer
from responses.test_supported_findings import _case


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", ["valid", "invalid", "budget", "missing"])
async def test_citation_protocol_has_one_bounded_repair_with_the_same_materials(repair):
    _, _, fixture, _ = await _case()

    class Model:
        def __init__(self):
            self.calls = []

        async def invoke(self, *, messages, **kwargs):
            self.calls.append(messages)
            if len(self.calls) == 2 and repair == "budget":
                raise ModelBudgetExceeded("model_calls")
            citation = "[1]" if len(self.calls) == 2 and repair in {"valid", "missing"} else "[99]"
            if len(self.calls) == 1 and repair == "missing":
                citation = "[n]"
            return AIMessage(content=json.dumps({
                "content": f"A {citation}.", "issues": [], "unanswered_points": []}))

    model = Model()
    args = dict(question="State A.", constraints=["Only this source"], content="A draft [1].",
                sources=["[1] A."], input_budget=8000, requirements=["A"])
    context = replace(fixture.context, model_gateway=model)
    if repair in {"valid", "missing"}:
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
        assert data["draft"] == "A draft [1]."
        assert data["answer_requirements"] == ["A"]
        assert "State A." in messages[-1].content


@pytest.mark.asyncio
async def test_valid_first_review_is_preserved_without_a_repair():
    _, _, fixture, _ = await _case()
    calls = []

    class Model:
        async def invoke(self, *, messages, **kwargs):
            calls.append(messages)
            return AIMessage(content=json.dumps({
                "content": "A [1].", "issues": [], "unanswered_points": ["B remains unknown"]}))

    reviewed = await review_answer(
        replace(fixture.context, model_gateway=Model()), question="State A and B.",
        constraints=[], content="A draft [1].", sources=["[1] A."], input_budget=8000)
    assert reviewed.content == "A [1]."
    assert reviewed.unanswered_points == ["B remains unknown"]
    assert len(calls) == 1
