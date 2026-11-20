"""Research hints must survive actual strategy dispatch and Gateway execution."""

import json

import pytest
from strategies.fixtures import ScriptedModelGateway, build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicOutcome
from deeptrace.harness.batch_collection import search_sources
from deeptrace.strategies import (
    build_multi_agent_research_graph,
    build_plan_execute_research_graph,
    build_workflow_research_graph,
)

QUERY = "Bose gas coherence 2026"
SEARCHES = ["Bose gas coherence 2026", "quantum quench dynamics 2026"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_dispatch_preserves_research_hints_through_real_gateway(mode):
    key = "assignments" if mode is ResearchMode.MULTI_AGENT else "queries"
    proposal = {
        key: [QUERY],
        "requirements": [{"id": "r1", "description": "Representative coherence result"}],
        "query_targets": {QUERY: ["r1"]},
        "research_brief": {
            "objective": "Representative coherence result", "scope": "2026 original papers",
            "answer_expectation": "Explain contribution with original sources",
            "source_policy": "research_results", "source_domains": ["arxiv.org"],
            "publication_years": [2026],
        },
        "task_briefs": {QUERY: {
            "objective": "Coherence", "boundary": "Bose gas only",
            "source_strategy": "Original papers", "expected_output": "Result and date",
            "search_queries": SEARCHES,
        }},
    }
    role = "supervisor" if mode is ResearchMode.MULTI_AGENT else "planner"
    fixture = build_gateway_fixture(model_gateway=ScriptedModelGateway({role: json.dumps(proposal)}))
    dispatched = []

    class Branch:
        async def ainvoke(self, data, config=None, **kwargs):
            task = data["topic_input"]
            dispatched.append(task)
            await search_sources({"topic_input": task, "messages": []}, fixture.context)
            return {"outcome": ResearchTopicOutcome(query=task.query)}

    factory = {
        ResearchMode.WORKFLOW: build_workflow_research_graph,
        ResearchMode.PLAN_EXECUTE: build_plan_execute_research_graph,
        ResearchMode.MULTI_AGENT: build_multi_agent_research_graph,
    }[mode]
    options = {} if mode is ResearchMode.WORKFLOW else (
        {"max_replans": 0} if mode is ResearchMode.PLAN_EXECUTE else {"max_follow_ups": 0})
    await factory(Branch(), **options).ainvoke({
        "run_id": "run-1", "thread_id": "thread-1", "question": "2026 original coherence papers",
        "current_date": "2026-10-11", "timezone": "Asia/Shanghai",
    }, context=fixture.context)
    assert len(dispatched) == 1
    task = dispatched[0]
    assert task.source_policy == "research_results"
    assert task.source_domains == ["arxiv.org"]
    assert task.publication_years == [2026]
    assert task.search_queries == SEARCHES
    assert set(fixture.search.calls) == {SEARCHES[0], "site:arxiv.org " + SEARCHES[1]}


def test_branch_context_projection_is_idempotent_and_explicit_root_values_win():
    from deeptrace.strategies.model_io import branch_context

    parent = {
        "question": "Original question", "query": QUERY,
        "research_brief": {"source_policy": "research_results", "source_domains": ["arxiv.org"],
                           "publication_years": [2026]},
        "task_briefs": {QUERY: {"search_queries": SEARCHES}},
    }
    first = branch_context(parent)
    assert branch_context(first) == first
    revised = branch_context({**first, **parent,
        "research_brief": {"source_policy": "general", "source_domains": [], "publication_years": []},
        "task_briefs": {QUERY: {"search_queries": []}},
    })
    assert revised["source_policy"] == "general"
    assert revised["source_domains"] == revised["publication_years"] == revised["search_queries"] == []
