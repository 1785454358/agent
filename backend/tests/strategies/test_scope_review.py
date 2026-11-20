"""A scope critic may narrow a plan, never silently change its authority."""

import copy
import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode
from deeptrace.strategies.evidence_evaluation import seal_initial_plan
from deeptrace.strategies.scope_review import review_plan_scope
from strategies.fixtures import build_gateway_fixture
from strategies.test_minimal_planning_contract import PLANNERS
from strategies.test_research_brief import QUERIES, payload

QUESTION = "Compare documented uses and prerequisites."


def review():
    return {"requirements": [{"id": "r2", "description": "Documented uses and prerequisites",
                               "request_excerpt": "uses and prerequisites"}],
            "excluded": [{"id": "r1", "reason": "An unrequested migration recipe"}]}


class ReviewModel:
    def __init__(self, response):
        self.response = response

    async def invoke(self, **kwargs):
        if isinstance(self.response, Exception):
            raise self.response
        return AIMessage(content=json.dumps(self.response))


async def run_review(response):
    queries, contract = seal_initial_plan(QUESTION, payload(), QUERIES)
    fixture = build_gateway_fixture(model_gateway=ReviewModel(response))
    state = {"question": QUESTION, "current_date": "2026-11-08", "timezone": "Asia/Shanghai",
             "run_id": "scope", "thread_id": "scope"}
    before = copy.deepcopy(contract)
    context = replace(fixture.context, research_completion_scope="scope_review")
    result = await review_plan_scope(state, context, queries, contract)
    assert contract == before
    return result, before


@pytest.mark.asyncio
async def test_review_prunes_only_excluded_targets_and_renumbers_retained_requirements():
    (queries, contract), before = await run_review(review())
    assert queries == [QUERIES[1]]
    assert [(r.id, r.description) for r in contract["requirements"]] == [
        ("r1", "Documented uses and prerequisites")]
    assert contract["query_targets"] == {QUERIES[1]: ["r1"]}
    assert contract["task_briefs"] == {QUERIES[1]: before["task_briefs"][QUERIES[1]]}
    assert contract["research_brief"] == before["research_brief"]


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["unknown_id", "omitted_id", "duplicate", "quote", "extra_authority", "failure"])
async def test_invalid_or_failed_scope_review_preserves_the_full_original_plan(problem):
    data = review()
    if problem == "unknown_id": data["requirements"][0]["id"] = "r6"
    elif problem == "omitted_id": data["excluded"] = []
    elif problem == "duplicate": data["excluded"][0]["id"] = "r2"
    elif problem == "quote": data["requirements"][0]["request_excerpt"] = "not in the user request"
    elif problem == "extra_authority": data["source_policy"] = "trust_all"
    else: data = RuntimeError("provider unavailable")
    (queries, contract), before = await run_review(data)
    assert queries == QUERIES
    assert contract["requirements"] == before["requirements"]
    assert contract["query_targets"] == before["query_targets"]
    assert contract["research_brief"] == before["research_brief"]
    assert "initial_scope_review_unavailable" in contract["diagnostic_gaps"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_each_strategy_applies_scope_review_before_discovery_dispatch(mode):
    factory, _, field, state_key = PLANNERS[mode]

    class Model:
        async def invoke(self, *, role, **kwargs):
            data = review() if role == "scope_reviewer" else {**payload(), field: QUERIES}
            return AIMessage(content=json.dumps(data))

    fixture = build_gateway_fixture(model_gateway=Model())
    context = replace(fixture.context, research_completion_scope="scope_review")
    result = await factory(3)({"question": QUESTION, "current_date": "2026-11-08",
                               "timezone": "Asia/Shanghai", "run_id": "scope", "thread_id": "scope"},
                              Runtime(context=context))
    assert result[state_key] == [QUERIES[1]]
    assert [(r.id, r.description) for r in result["requirements"]] == [
        ("r1", "Documented uses and prerequisites")]
