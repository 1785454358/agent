"""Parent source grants and current gaps reach every real research branch."""

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.context import HarnessContext
from deeptrace.strategies.common import research_input_from_state
from deeptrace.strategies.model_io import branch_context
from deeptrace.strategies.multi_agent.nodes import (
    build_researcher_node,
    route_after_follow_up,
    route_researchers,
)
from deeptrace.strategies.plan_execute.nodes import build_execute_task_node
from deeptrace.strategies.workflow.nodes import build_research_topic_node, route_topics
from deeptrace.tools.evidence_store import EvidenceDraft, InMemoryEvidenceStore
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture


def _state():
    return {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": "Explain Store",
        "evidence_contract_version": 3,
        "current_date": "2026-10-02",
        "timezone": "Asia/Shanghai",
        "requirements": [{"id": "r1", "description": "Explain cross-thread storage"}],
        "target_requirement_ids": ["r1"],
        "unresolved_gaps": ["Need the persistence scope"],
    }


def test_current_gaps_are_not_discarded_at_the_strategy_boundary():
    assert research_input_from_state(_state()).unresolved_gaps == [
        "Need the persistence scope"
    ]


@pytest.mark.asyncio
async def test_host_page_quota_comes_from_context_not_model_or_state():
    from dataclasses import replace
    from deeptrace.strategies.common import validated_branch_context

    fixture = build_gateway_fixture()
    context = replace(fixture.context, research_max_pages=6)
    result = await validated_branch_context({**_state(), "max_pages": 999}, context)
    assert result["max_pages"] == 6


def test_branch_context_preserves_bounded_targeted_requirements_and_gaps():
    context = branch_context(_state())
    assert context.get("requirements") == _state()["requirements"]
    assert context.get("target_requirement_ids") == ["r1"]
    assert context.get("research_gaps") == ["Need the persistence scope"]


def test_branch_context_keeps_parent_background_across_fanout():
    context = branch_context(
        {"original_task": "original", "context_notes": ["prior background"]}
    )
    assert context["context_notes"] == ["prior background"]


def test_follow_up_preserves_both_prior_and_new_parent_sources():
    state = {
        **_state(),
        "assignments": ["Store"],
        "round_number": 1,
        "prior_evidence_ids": ["prior"],
        "evidence_ids": ["new"],
    }
    branch = route_after_follow_up(state)[0].arg
    assert branch.get("prior_evidence_ids") == ["prior", "new"]


@pytest.mark.asyncio
async def test_host_selects_only_current_parent_sources_not_arbitrary_dto_grants():
    from deeptrace.strategies.common import validated_branch_context

    fixture = build_gateway_fixture()
    draft = EvidenceDraft(
        canonical_url="https://example.com/store",
        title="Store",
        media_type="text/plain",
        body="old",
        fetched_at=FIXED_NOW,
        source_quality=0.9,
    )
    old = await fixture.evidence_store.ingest(TENANT_ID, draft)
    current = await fixture.evidence_store.ingest(
        TENANT_ID, draft.model_copy(update={"body": "current"})
    )
    foreign = await fixture.evidence_store.ingest(
        "other",
        draft.model_copy(update={"canonical_url": "https://example.com/foreign"}),
    )
    secret = await fixture.evidence_store.ingest(
        TENANT_ID,
        draft.model_copy(
            update={
                "canonical_url": "https://example.com/unrelated",
                "body": "not selected",
            }
        ),
    )
    state = {
        **_state(),
        "prior_evidence_ids": [old.id, foreign.id, "missing"],
        "evidence_ids": [current.id],
        "authorized_evidence_ids": [secret.id],
    }
    context = await validated_branch_context(state, fixture.context)
    assert context["authorized_evidence_ids"] == [current.id]


@pytest.mark.asyncio
async def test_valid_parent_sources_are_validated_in_one_batch():
    from deeptrace.strategies.common import validated_branch_context

    class CountingStore(InMemoryEvidenceStore):
        def __init__(self):
            super().__init__()
            self.reads = []

        async def get(self, tenant_id, evidence_id):
            self.reads.append("single")
            return await super().get(tenant_id, evidence_id)

        async def get_many(self, tenant_id, evidence_ids):
            self.reads.append("batch")
            return await super().get_many(tenant_id, evidence_ids)

    store = CountingStore()
    fixture = build_gateway_fixture(evidence_store=store)
    ids = []
    for index in range(3):
        record = await store.ingest(
            TENANT_ID,
            EvidenceDraft(
                canonical_url=f"https://example.com/store-{index}",
                title="Store",
                media_type="text/plain",
                body="Store",
                fetched_at=FIXED_NOW,
                source_quality=0.9,
            ),
        )
        ids.append(record.id)
    result = await validated_branch_context(
        {"prior_evidence_ids": ids}, fixture.context
    )
    assert result["authorized_evidence_ids"] == ids
    assert store.reads == ["batch"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_parent_body_is_readable_in_actual_strategy_branch_without_refetch(mode):
    observed = []
    source_id = None

    class ParentReadingModel:
        async def invoke(self, *, role, messages, tools=None):
            text = "\n".join(str(message.content) for message in messages)
            assert "Explain Store" in text
            assert "Explain cross-thread storage" in text
            assert "Need the persistence scope" in text
            assert source_id in text
            results = [m for m in messages if isinstance(m, ToolMessage)]
            if results:
                data = json.loads(results[-1].content)
                observed.append(data)
                return AIMessage(content="done")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_evidence",
                        "args": {"evidence_id": source_id},
                        "id": "read-parent",
                    }
                ],
            )

    fixture = build_gateway_fixture(model_gateway=ParentReadingModel())
    draft = EvidenceDraft(
        canonical_url="https://example.com/store",
        title="Store",
        media_type="text/plain",
        body="Store keeps cross-thread facts.",
        fetched_at=FIXED_NOW,
        source_quality=0.9,
    )
    prior = await fixture.evidence_store.ingest(TENANT_ID, draft)
    source_id = prior.id
    state = {
        **_state(),
        "prior_evidence_ids": [prior.id, "missing"],
        "queries": ["Store"],
        "assignments": ["Store"],
        "current_task": "Store",
    }
    graph = build_research_agent_graph(max_iterations=2, completion_nudge_limit=0)
    if mode is ResearchMode.WORKFLOW:
        branch = route_topics(state)[0].arg
        node = build_research_topic_node(graph)
    elif mode is ResearchMode.MULTI_AGENT:
        branch = route_researchers(state)[0].arg
        node = build_researcher_node(graph)
    else:
        branch = state
        node = build_execute_task_node(graph)
    parent = StateGraph(dict, context_schema=HarnessContext)

    async def run_branch(state, runtime: Runtime[HarnessContext], config):
        return await node(state, runtime, config)

    parent.add_node("research", run_branch)
    parent.add_edge(START, "research")
    parent.add_edge("research", END)
    result = await parent.compile().ainvoke(branch, context=fixture.context)
    assert observed, result
    assert observed[0]["ok"], observed[0]
    assert "Store keeps cross-thread facts." in observed[0]["preview"]
    assert result["evidence_ids"] == [prior.id]
    assert fixture.fetcher.calls == []
    assert fixture.gateway.calls[0]["evidence_authorization"].evidence_ids == frozenset(
        [prior.id]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("requirements", [{"id": "r1", "description": "x"}] * 2),
        ("target_requirement_ids", ["r1", "r1"]),
        ("target_requirement_ids", ["r7"]),
        ("authorized_evidence_ids", ["e-1", "e-1"]),
        ("authorized_evidence_ids", [f"e-{index}" for index in range(101)]),
        ("research_gaps", ["x" * 501]),
    ],
)
def test_branch_dto_rejects_unbounded_or_ambiguous_context(field, value):
    from pydantic import ValidationError

    assert field in ResearchTopicInput.model_fields, (
        "branch context contract not implemented"
    )
    with pytest.raises(ValidationError):
        ResearchTopicInput(
            run_id="run-1",
            thread_id="thread-1",
            query="q",
            mode=ResearchMode.PLAN_EXECUTE,
            caller_id="plan-execute-executor",
            **{field: value},
        )
