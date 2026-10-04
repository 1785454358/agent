"""Actual reading, not manually registering a guess, permits branch completion."""

import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResearchMode
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from harness.test_agent_invariants import Model, assert_pairs, call
from harness.test_finish_research import finish_call
from harness.test_record_findings_loop import seed, task_for


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_read_then_finish_without_candidate_registration(mode):
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    model = Model(
        AIMessage(
            content="",
            tool_calls=[call("read_evidence", {"evidence_id": record.id}, "read")],
        ),
        AIMessage(content="", tool_calls=[finish_call()]),
    )
    result = await build_research_agent_graph(max_iterations=2).ainvoke(
        {"topic_input": task_for(mode, record)},
        context=replace(fixture.context, model_gateway=model),
    )
    assert result["outcome"].agent_outcome.stop_reason == "completed"
    assert result["outcome"].agent_outcome.iterations == 2
    assert result["outcome"].research_findings == []
    assert result["outcome"].read_anchors
    assert_pairs(result["messages"])
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(result))
    assert restored["outcome"].read_anchors == result["outcome"].read_anchors


@pytest.mark.asyncio
async def test_authorized_but_unread_source_does_not_permit_finish():
    fixture = build_gateway_fixture()
    record, _ = await seed(fixture)
    result = await build_research_agent_graph(max_iterations=1).ainvoke(
        {"topic_input": task_for(ResearchMode.WORKFLOW, record)},
        context=replace(
            fixture.context,
            model_gateway=Model(AIMessage(content="", tool_calls=[finish_call()])),
        ),
    )
    assert result["outcome"].agent_outcome.status == "partial"
    assert (
        json.loads(result["messages"][-1].content)["error_code"]
        == "finish_no_valid_reads"
    )
