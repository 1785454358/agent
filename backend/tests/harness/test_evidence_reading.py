"""The actual Agent Loop delivers source bodies through authorized reads."""

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput, ToolName
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.tools.evidence_store import EvidenceDraft


def _task(mode):
    callers = {
        ResearchMode.WORKFLOW: "workflow-graph",
        ResearchMode.PLAN_EXECUTE: "plan-execute-executor",
        ResearchMode.MULTI_AGENT: "researcher-0",
    }
    return ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="Store",
        mode=mode,
        caller_id=callers[mode],
        original_task="Explain Store",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_fetched_tail_is_visible_only_after_read_in_each_mode(mode):
    fact = "Store keeps cross-thread facts."
    observed = []

    class ReadingModel:
        async def invoke(self, *, role, messages, tools=None):
            assert role == "researcher"
            # Behavioral gate: no readable body is given by fetch metadata.
            results = [m for m in messages if isinstance(m, ToolMessage)]
            if not results:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_web",
                            "args": {"query": "Store"},
                            "id": "search",
                        }
                    ],
                )
            data = json.loads(results[-1].content)
            if data["tool"] == "search_web":
                url = json.loads(data["preview"])["results"][0]["url"]
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "fetch_page", "args": {"url": url}, "id": "fetch"}
                    ],
                )
            if data["tool"] == "fetch_page":
                assert fact not in data["preview"]
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_evidence",
                            "args": {"evidence_id": data["evidence_ids"][0]},
                            "id": "read",
                        }
                    ],
                )
            observed.append(data)
            return AIMessage(content="done")

    fixture = build_gateway_fixture(
        model_gateway=ReadingModel(),
        default_search_results=[{"url": "https://example.com/store", "title": "Store"}],
        pages={"https://example.com/store": "Unrelated.\n\n" * 700 + fact},
    )
    result = await build_research_agent_graph().ainvoke(
        {"topic_input": _task(mode)}, context=fixture.context
    )
    assert observed[0]["ok"], observed[0]
    assert fact in observed[0]["preview"]
    assert result["outcome"].agent_outcome.status == "completed"
    assert len(result["outcome"].evidence_ids) == 1
    assert fixture.fetcher.calls == ["https://example.com/store"]
    read = fixture.gateway.calls[-1]
    assert read["request"].tool is ToolName.READ_EVIDENCE
    assert read["request"].arguments["query"] == "Store"
    assert read["evidence_authorization"].evidence_ids == frozenset(
        result["outcome"].evidence_ids
    )


@pytest.mark.asyncio
async def test_known_ungranted_workspace_id_never_enters_agent_messages():
    observed = []
    fixture = build_gateway_fixture()
    secret = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/private",
            title="Private",
            media_type="text/plain",
            body="private source body",
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )

    class UnauthorizedModel:
        async def invoke(self, *, role, messages, tools=None):
            results = [m for m in messages if isinstance(m, ToolMessage)]
            if results:
                observed.append(json.loads(results[-1].content))
                return AIMessage(content="no source")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_evidence",
                        "args": {"evidence_id": secret.id},
                        "id": "read",
                    }
                ],
            )

    from dataclasses import replace

    context = replace(fixture.context, model_gateway=UnauthorizedModel())
    await build_research_agent_graph(max_iterations=2).ainvoke(
        {"topic_input": _task(ResearchMode.PLAN_EXECUTE)}, context=context
    )
    assert observed[0]["error_code"] == "evidence_not_authorized"
    assert "private source body" not in json.dumps(observed)
