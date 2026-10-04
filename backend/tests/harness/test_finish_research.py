"""Completion is a checked local transition, not a model's success assertion."""

import json
from dataclasses import replace

import pytest
from deeptrace.domain import ResearchMode
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.tools.evidence_store import EvidenceDraft
from langchain_core.messages import AIMessage, ToolMessage
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture

from harness.test_agent_invariants import Model, assert_pairs, call
from harness.test_record_findings_loop import seed, task_for


def record_call(ref="n1"):
    return call(
        "record_findings",
        {
            "findings": [
                {
                    "claim": "The operation requires its context key.",
                    "refs": [ref],
                    "confidence": 0.8,
                }
            ]
        },
        "record",
    )


def finish_call(**args):
    return call(
        "finish_research", args or {"summary": "Supported branch conclusion"}, "finish"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_last_turn_records_and_finishes_with_paired_checkpoint(mode):
    fixture = build_gateway_fixture()
    record, body = await seed(fixture)
    model = Model(
        AIMessage(
            content="",
            tool_calls=[call("read_evidence", {"evidence_id": record.id}, "read")],
        ),
        AIMessage(
            content="",
            tool_calls=[
                record_call(),
                call(
                    "write_todos",
                    {
                        "todos": [
                            {
                                "content": "Read and record context key",
                                "status": "completed",
                            }
                        ],
                    },
                    "todo",
                ),
                finish_call(),
            ],
        ),
    )
    result = await build_research_agent_graph(max_iterations=2).ainvoke(
        {"topic_input": task_for(mode, record)},
        context=replace(fixture.context, model_gateway=model),
    )
    outcome = result["outcome"].agent_outcome
    assert outcome.stop_reason == "completed"
    assert outcome.iterations == 2
    assert outcome.summary == "Supported branch conclusion"
    assert result["outcome"].research_findings[0].supports[0].quote == body
    assert_pairs(result["messages"])
    payloads = [
        json.loads(m.content) for m in result["messages"] if isinstance(m, ToolMessage)
    ]
    assert payloads[-1]["ok"] is True
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(result))
    assert restored["outcome"].agent_outcome.summary == outcome.summary
    events = [p for k, p in fixture.events.events if k == "agent.local_tool"]
    assert events[-1]["tool"] == "finish_research" and events[-1]["ok"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tail,code",
    [
        ([record_call("n99"), finish_call()], "finish_prior_call_failed"),
        (
            [
                record_call(),
                call(
                    "write_todos",
                    {"todos": [{"content": "Still researching", "status": "pending"}]},
                    "todo",
                ),
                finish_call(),
            ],
            "finish_open_todos",
        ),
        ([record_call(), finish_call(summary=" ")], "invalid_arguments"),
        (
            [record_call(), finish_call(summary="done", extra="bad")],
            "invalid_arguments",
        ),
        (
            [
                record_call(),
                finish_call(),
                call(
                    "write_todos",
                    {"todos": [{"content": "done", "status": "completed"}]},
                    "todo",
                ),
            ],
            "invalid_finish_batch",
        ),
        (
            [
                record_call(),
                finish_call(),
                call("finish_research", {"summary": "twice"}, "finish2"),
            ],
            "invalid_finish_batch",
        ),
    ],
)
async def test_invalid_finish_preserves_partial_and_paired_results(tail, code):
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    model = Model(
        AIMessage(
            content="",
            tool_calls=[call("read_evidence", {"evidence_id": record.id}, "read")],
        ),
        AIMessage(content="", tool_calls=tail),
    )
    result = await build_research_agent_graph(max_iterations=2).ainvoke(
        {"topic_input": task_for(ResearchMode.WORKFLOW, record)},
        context=replace(fixture.context, model_gateway=model),
    )
    assert result["outcome"].agent_outcome.status == "partial"
    results = [
        json.loads(m.content) for m in result["messages"] if isinstance(m, ToolMessage)
    ]
    assert code in [p.get("error_code") for p in results]
    assert_pairs(result["messages"])


@pytest.mark.asyncio
async def test_read_and_finish_cannot_complete_in_one_batch():
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    model = Model(
        AIMessage(
            content="",
            tool_calls=[
                call("read_evidence", {"evidence_id": record.id}, "read"),
                record_call(),
                finish_call(),
            ],
        )
    )
    result = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": task_for(ResearchMode.WORKFLOW, record)},
        context=replace(fixture.context, model_gateway=model),
    )
    assert result["outcome"].agent_outcome.status == "partial"
    results = [
        json.loads(m.content) for m in result["messages"] if isinstance(m, ToolMessage)
    ]
    assert results[-1]["error_code"] == "invalid_finish_batch"
    assert result["outcome"].research_findings == []
    assert_pairs(result["messages"])


@pytest.mark.asyncio
async def test_finish_revalidates_superseded_source():
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)

    class UpdatingModel(Model):
        async def invoke(self, **kwargs):
            response = await super().invoke(**kwargs)
            if len(self.calls) == 3:
                await fixture.evidence_store.ingest(
                    TENANT_ID,
                    EvidenceDraft(
                        canonical_url=record.canonical_url,
                        title=record.title,
                        body="Changed source",
                        media_type=record.media_type,
                        fetched_at=FIXED_NOW,
                        source_quality=0.9,
                    ),
                )
            return response

    model = UpdatingModel(
        AIMessage(
            content="",
            tool_calls=[call("read_evidence", {"evidence_id": record.id}, "read")],
        ),
        AIMessage(content="", tool_calls=[record_call()]),
        AIMessage(content="", tool_calls=[finish_call()]),
    )
    result = await build_research_agent_graph(max_iterations=3).ainvoke(
        {"topic_input": task_for(ResearchMode.WORKFLOW, record)},
        context=replace(fixture.context, model_gateway=model),
    )
    assert result["outcome"].agent_outcome.status == "partial"
    last = json.loads(result["messages"][-1].content)
    assert last["error_code"] == "finish_no_valid_reads"
