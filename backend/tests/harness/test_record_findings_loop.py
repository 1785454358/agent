"""Real branch-loop recording, isolation and terminal checkpoint delivery."""

import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.tools.evidence_store import EvidenceDraft


async def seed(fixture):
    body = "The operation requires its context key. 中文🙂"
    record = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/operation",
            title="Operation",
            body=body,
            media_type="text/plain",
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )
    return record, body


def task_for(mode, record):
    return ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="operation",
        mode=mode,
        caller_id={
            ResearchMode.WORKFLOW: "workflow-graph",
            ResearchMode.PLAN_EXECUTE: "plan-execute-executor",
            ResearchMode.MULTI_AGENT: "researcher-0",
        }[mode],
        authorized_evidence_ids=[record.id],
        evidence_contract_version=3,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_recorded_fact_survives_iteration_limit_and_checkpoint(mode):
    fixture = build_gateway_fixture()
    record, body = await seed(fixture)

    class Reader:
        async def invoke(self, *, role, messages, tools=None):
            returned = [m for m in messages if isinstance(m, ToolMessage)]
            if not returned:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "read",
                            "name": "read_evidence",
                            "args": {"evidence_id": record.id, "find": "context key"},
                        }
                    ],
                )
            payload = json.loads(returned[-1].content)
            assert payload["ok"], payload
            preview = json.loads(payload["preview"])
            assert "ref" in preview["passages"][0]
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "record",
                        "name": "record_findings",
                        "args": {
                            "findings": [
                                {
                                    "claim": "The operation requires its context key.",
                                    "refs": [preview["passages"][0]["ref"]],
                                    "confidence": 0.8,
                                }
                            ]
                        },
                    }
                ],
            )

    result = await build_research_agent_graph(max_iterations=2).ainvoke(
        {"topic_input": task_for(mode, record)},
        context=replace(fixture.context, model_gateway=Reader()),
    )
    outcome = result["outcome"]
    assert outcome.agent_outcome.stop_reason == "iteration_limit"
    assert outcome.executed_steps == 2
    assert len(outcome.research_findings) == 1
    support = outcome.research_findings[0].supports[0]
    assert support.quote == body
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(result))
    assert restored["outcome"].research_findings == outcome.research_findings
    assert len(restored["research_refs"]) == 1
    assert not fixture.fetcher.calls
    local = [p for kind, p in fixture.events.events if kind == "agent.local_tool"]
    assert len(local) == 1
    assert local[0]["tool"] == "record_findings" and local[0]["ok"]


@pytest.mark.asyncio
async def test_same_batch_read_cannot_authorize_record_or_fake_completion():
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)

    class Reader:
        async def invoke(self, *, role, messages, tools=None):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "read",
                        "name": "read_evidence",
                        "args": {"evidence_id": record.id},
                    },
                    {
                        "id": "record",
                        "name": "record_findings",
                        "args": {
                            "findings": [
                                {"claim": "Unseen", "refs": ["n1"], "confidence": 1}
                            ]
                        },
                    },
                ],
            )

    result = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": task_for(ResearchMode.WORKFLOW, record)},
        context=replace(fixture.context, model_gateway=Reader()),
    )
    assert getattr(result["outcome"], "research_findings", []) == []
    results = [
        json.loads(m.content) for m in result["messages"] if isinstance(m, ToolMessage)
    ]
    assert results[-1]["error_code"] == "invalid_read_reference"
