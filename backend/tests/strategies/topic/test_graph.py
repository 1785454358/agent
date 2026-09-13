from __future__ import annotations

import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.strategies.topic.graph import build_research_topic_graph
from deeptrace.tools.policy import CallerRole, UrlAuthorizationSource

from strategies.fixtures import TENANT_ID, build_gateway_fixture


def _long_results(count: int, snippet_length: int) -> list[dict[str, str]]:
    return [
        {
            "url": f"https://example.com/page-{index}",
            "title": f"Page {index}",
            "snippet": "s" * snippet_length,
        }
        for index in range(count)
    ]


async def _run_topic(
    fixture,
    *,
    query: str = "LangGraph harness",
    max_pages: int = 3,
    mode: ResearchMode = ResearchMode.WORKFLOW,
    checkpointer=None,
):
    graph = build_research_topic_graph(checkpointer=checkpointer)
    topic_input = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query=query,
        max_pages=max_pages,
        mode=mode,
        caller_id="workflow-graph",
    )
    config = (
        {"configurable": {"thread_id": "topic-thread"}} if checkpointer else None
    )
    result = await graph.ainvoke(
        {"topic_input": topic_input}, config=config, context=fixture.context
    )
    return result["outcome"]


@pytest.mark.asyncio
async def test_search_precedes_selection_and_fetches_fan_out() -> None:
    fixture = build_gateway_fixture(
        search_results={
            "LangGraph harness": [
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "snippet": "first",
                },
                {
                    "url": "https://example.com/b",
                    "title": "B",
                    "snippet": "second",
                },
            ]
        },
        pages={"https://example.com/a": "body-a", "https://example.com/b": "body-b"},
    )

    outcome = await _run_topic(fixture, max_pages=2)

    assert [call["request"].tool.value for call in fixture.gateway.calls] == [
        "search_web",
        "fetch_page",
        "fetch_page",
    ]
    assert fixture.search.calls == ["LangGraph harness"]
    assert fixture.fetcher.calls == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert set(outcome.evidence_ids) == {
        await fixture.evidence_id_for("https://example.com/a"),
        await fixture.evidence_id_for("https://example.com/b"),
    }
    assert outcome.errors == []
    assert outcome.executed_steps == 3
    assert outcome.attempted_urls == [
        "https://example.com/a",
        "https://example.com/b",
    ]


@pytest.mark.asyncio
async def test_gateway_receives_tenant_caller_and_search_only_authorization() -> None:
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "body-a"},
    )

    await _run_topic(fixture)

    for call in fixture.gateway.calls:
        assert call["tenant_id"] == TENANT_ID
    search_call, fetch_call = fixture.gateway.calls[0], fixture.gateway.calls[1]
    assert search_call["caller"].role is CallerRole.WORKFLOW_GRAPH
    assert search_call["caller"].mode is ResearchMode.WORKFLOW
    assert search_call["caller"].caller_id == "workflow-graph"
    assert search_call.get("authorization") is None
    assert fetch_call["request"].tool.value == "fetch_page"
    assert fetch_call["authorization"].source is UrlAuthorizationSource.SEARCH_RESULT
    assert fetch_call["authorization"].urls == frozenset(
        {"https://example.com/a"}
    )
    assert fetch_call["request"].arguments == {"url": "https://example.com/a"}


@pytest.mark.asyncio
async def test_caller_role_follows_the_selected_research_mode() -> None:
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "body-a"},
    )

    outcome = await _run_topic(fixture, mode=ResearchMode.MULTI_AGENT)

    assert fixture.gateway.calls[0]["caller"].role is CallerRole.MULTI_AGENT_RESEARCHER
    assert outcome.errors == []


@pytest.mark.asyncio
async def test_tool_call_ids_are_deterministic_across_runs() -> None:
    search_results = [
        {"url": "https://example.com/a", "title": "A", "snippet": "s"},
        {"url": "https://example.com/b", "title": "B", "snippet": "s"},
    ]

    first = build_gateway_fixture(default_search_results=search_results)
    second = build_gateway_fixture(default_search_results=search_results)
    await _run_topic(first)
    await _run_topic(second)

    first_ids = [call["request"].call_id for call in first.gateway.calls]
    second_ids = [call["request"].call_id for call in second.gateway.calls]
    assert first_ids == second_ids
    assert len(set(first_ids)) == len(first_ids)
    assert all(call_id.startswith("call-") for call_id in first_ids)


@pytest.mark.asyncio
async def test_malformed_search_preview_records_stable_error() -> None:
    fixture = build_gateway_fixture(
        default_search_results=_long_results(count=8, snippet_length=600)
    )

    outcome = await _run_topic(fixture, max_pages=8)

    assert outcome.evidence_ids == []
    assert outcome.attempted_urls == []
    assert fixture.fetcher.calls == []
    assert [(error.stage, error.target, error.code) for error in outcome.errors] == [
        ("search", "", "malformed_search_preview")
    ]
    assert outcome.executed_steps == 1


@pytest.mark.asyncio
async def test_duplicate_and_unsafe_urls_are_dropped() -> None:
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/dup", "title": "D", "snippet": "s"},
            {"url": "https://example.com/dup", "title": "D", "snippet": "s"},
            {"url": "http://localhost/secret", "title": "L", "snippet": "s"},
            {"url": "https://example.com/ok", "title": "O", "snippet": "s"},
        ],
        pages={"https://example.com/dup": "body-dup"},
    )

    outcome = await _run_topic(fixture, max_pages=4)

    assert fixture.fetcher.calls == [
        "https://example.com/dup",
        "https://example.com/ok",
    ]
    assert outcome.attempted_urls == [
        "https://example.com/dup",
        "https://example.com/ok",
    ]
    assert outcome.errors == []


@pytest.mark.asyncio
async def test_empty_search_results_record_a_stable_error() -> None:
    fixture = build_gateway_fixture(default_search_results=[])

    outcome = await _run_topic(fixture)

    assert outcome.evidence_ids == []
    assert outcome.attempted_urls == []
    assert [(error.stage, error.code) for error in outcome.errors] == [
        ("search", "no_search_results")
    ]
    assert outcome.executed_steps == 1


@pytest.mark.asyncio
async def test_partial_fetch_failure_keeps_sibling_evidence() -> None:
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"},
            {"url": "https://example.com/b", "title": "B", "snippet": "s"},
        ],
        pages={"https://example.com/a": "body-a"},
        fetch_failures={"https://example.com/b": "empty"},
    )

    outcome = await _run_topic(fixture)

    assert outcome.evidence_ids == [await fixture.evidence_id_for("https://example.com/a")]
    assert [(error.stage, error.target, error.code) for error in outcome.errors] == [
        ("fetch", "https://example.com/b", "empty_page")
    ]
    assert outcome.executed_steps == 3


@pytest.mark.asyncio
async def test_transient_fetch_errors_are_retried_at_node_level() -> None:
    """provider_error retries 3x via RetryPolicy, then the topic graph raises."""
    import pytest as _pytest

    from deeptrace.strategies.topic.nodes import TransientToolError

    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"},
            {"url": "https://example.com/b", "title": "B", "snippet": "s"},
        ],
        pages={"https://example.com/a": "body-a"},
        fetch_failures={"https://example.com/b": "raise"},
    )
    graph = build_research_topic_graph()
    topic_input = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="LangGraph harness",
        max_pages=2,
        mode=ResearchMode.WORKFLOW,
        caller_id="workflow-graph",
    )

    with _pytest.raises(TransientToolError):
        await graph.ainvoke(
            {"topic_input": topic_input}, context=fixture.context
        )

    # every retry truly re-executed the provider (recoverable ledger semantics)
    assert fixture.fetcher.calls.count("https://example.com/b") == 3
    # sibling evidence from the successful branch is durable
    assert fixture.evidence_store._records  # evidence ingested for url a


@pytest.mark.asyncio
async def test_search_transient_failure_is_retried_then_recorded() -> None:
    import pytest as _pytest

    from deeptrace.strategies.topic.nodes import TransientToolError

    fixture = build_gateway_fixture(search_fail=True)
    graph = build_research_topic_graph()
    topic_input = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="LangGraph harness",
        mode=ResearchMode.WORKFLOW,
        caller_id="workflow-graph",
    )

    with _pytest.raises(TransientToolError):
        await graph.ainvoke(
            {"topic_input": topic_input}, context=fixture.context
        )

    # the search provider was truly re-executed on every retry attempt
    assert len(fixture.search.calls) == 3


@pytest.mark.asyncio
async def test_max_pages_bounds_the_fetch_fanout() -> None:
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": f"https://example.com/page-{index}", "title": str(index), "snippet": "s"}
            for index in range(6)
        ]
    )

    outcome = await _run_topic(fixture, max_pages=2)

    assert fixture.fetcher.calls == [
        "https://example.com/page-0",
        "https://example.com/page-1",
    ]
    assert len(outcome.evidence_ids) == 2


@pytest.mark.asyncio
async def test_topic_checkpoint_keeps_references_and_never_bodies() -> None:
    fixture = build_gateway_fixture(
        default_search_results=[
            {"url": "https://example.com/a", "title": "A", "snippet": "s"}
        ],
        pages={"https://example.com/a": "unique-evidence-body-marker"},
    )
    checkpointer = InMemorySaver()

    outcome = await _run_topic(fixture, checkpointer=checkpointer)

    assert len(outcome.evidence_ids) == 1
    snapshot = await build_research_topic_graph(checkpointer=checkpointer).aget_state(
        {"configurable": {"thread_id": "topic-thread"}}
    )
    serialized = json.dumps(snapshot.values, default=str, ensure_ascii=False)
    assert "unique-evidence-body-marker" not in serialized
    assert snapshot.values["outcome"].query == "LangGraph harness"
