"""A successful local read must survive the actual research graph boundary."""

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.tools.evidence_store import EvidenceDraft


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_successful_read_range_survives_branch_outcome_and_checkpoint(mode):
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(
        TENANT_ID,
        EvidenceDraft(
            canonical_url="https://example.com/read",
            title="Read",
            media_type="text/plain",
            body="prefix:`key`\nnot optional. 🧭",
            fetched_at=FIXED_NOW,
            source_quality=0.9,
        ),
    )

    class Reader:
        async def invoke(self, *, role, messages, tools=None):
            returned = [m for m in messages if isinstance(m, ToolMessage)]
            if returned:
                payload = json.loads(returned[-1].content)
                assert payload["ok"]
                preview = json.loads(payload["preview"])
                assert preview["passages"][0]["text"] == "`key`\nnot op"
                return AIMessage(content="done")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "read",
                        "name": "read_evidence",
                        "args": {"evidence_id": record.id, "start": 7, "limit": 12},
                    }
                ],
            )

    from dataclasses import replace

    callers = {
        ResearchMode.WORKFLOW: "workflow-graph",
        ResearchMode.PLAN_EXECUTE: "plan-execute-executor",
        ResearchMode.MULTI_AGENT: "researcher-0",
    }
    task = ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="Read",
        mode=mode,
        caller_id=callers[mode],
        authorized_evidence_ids=[record.id],
    )
    result = await build_research_agent_graph().ainvoke(
        {"topic_input": task}, context=replace(fixture.context, model_gateway=Reader())
    )
    anchors = getattr(result["outcome"], "read_anchors", [])
    assert [(a.start, a.end) for a in anchors] == [(7, 19)]
    assert anchors[0].evidence_id == record.id
    assert anchors[0].version == record.version
    assert anchors[0].content_hash == record.content_hash
    assert result["outcome"].executed_steps == 1
    serializer = create_harness_checkpoint_serializer()
    restored = serializer.loads_typed(serializer.dumps_typed(result["outcome"]))
    assert restored.read_anchors == anchors
    assert "quote" not in anchors[0].model_dump()
    assert "text" not in anchors[0].model_dump()


@pytest.mark.parametrize(
    "damage",
    [
        "truncated",
        "wrong_source",
        "boolean_version",
        "negative",
        "text_length",
        "historical",
    ],
)
def test_corrupt_read_preview_never_becomes_read_proof(damage):
    from deeptrace.harness.read_anchors import capture_read_anchors

    payload = {
        "evidence_id": "source",
        "version": 1,
        "content_hash": "hash",
        "historical": False,
        "selection": {"body_length": 19},
        "passages": [
            {
                "evidence_id": "source",
                "version": 1,
                "content_hash": "hash",
                "start": 7,
                "end": 19,
                "text": "`key`\nnot op",
            }
        ],
    }
    if damage == "wrong_source":
        payload["evidence_id"] = "other"
    elif damage == "boolean_version":
        payload["version"] = True
    elif damage == "negative":
        payload["passages"][0]["start"] = -1
    elif damage == "text_length":
        payload["passages"][0]["text"] = "made up"
    elif damage == "historical":
        payload["historical"] = True
    preview = json.dumps(payload)
    if damage == "truncated":
        preview = preview[:-1]
    anchors, diagnostics = capture_read_anchors(preview, "source")
    assert anchors == []
    assert "invalid_read_anchor_preview" in diagnostics


def test_replayed_reads_are_unique_bounded_and_stable():
    from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor, merge_read_anchors

    anchors = [
        ReadEvidenceAnchor(
            evidence_id="source", version=1, content_hash="hash", start=i, end=i + 1
        )
        for i in range(70)
    ]
    first = merge_read_anchors([], anchors[:30])
    merged = merge_read_anchors(first, [*anchors[:30], *anchors[30:]])
    assert [(a.start, a.end) for a in merged] == [(i, i + 1) for i in range(64)]
    assert merge_read_anchors(merged, anchors) == merged
