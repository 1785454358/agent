"""Scientific researchers hand read originals to the central evaluator once."""

import json

import pytest
from langchain_core.messages import AIMessage
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_research import build_batch_research_graph


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy,supplement,expected_calls",
    [
        ("research_results", False, 1),
        ("general", True, 0),
    ],
)
async def test_handoff_keeps_read_anchors_without_duplicate_model_summary(
    policy, supplement, expected_calls
):
    class SelectingOnly:
        def __init__(self):
            self.calls = []

        async def invoke(self, *, role, messages, tools=None):
            self.calls.append(str(messages[-1].content))
            assert "SOURCE_CANDIDATES_JSON:" in self.calls[-1]
            return AIMessage(content=json.dumps({"selected": ["c1"]}))

    model = SelectingOnly()
    body = (
        "Published: 3 June 2026. We measured a correlation under cryogenic conditions."
    )
    url = "https://example.com/original-paper"
    fixture = build_gateway_fixture(
        model_gateway=model,
        default_search_results=[{"url": url, "title": "A concrete experiment"}],
        pages={url: body},
    )
    task = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="correlation 2026 paper",
        mode=ResearchMode.PLAN_EXECUTE,
        caller_id="plan-execute-executor",
        source_policy=policy,
        requirements=[{"id": "r1", "description": "What was measured?"}],
        target_requirement_ids=["r1"],
        research_gaps=["r1:missing:Need original evidence"] if supplement else [],
    )
    result = await build_batch_research_graph().ainvoke(
        {"topic_input": task}, context=fixture.context
    )
    assert len(model.calls) == expected_calls
    outcome = result["outcome"]
    assert outcome.plan_complete
    assert outcome.agent_outcome.stop_reason == "completed"
    assert outcome.read_anchors and outcome.evidence_ids
    for anchor in outcome.read_anchors:
        assert body[anchor.start : anchor.end]
    assert not outcome.research_findings
