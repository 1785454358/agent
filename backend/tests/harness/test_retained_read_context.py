"""Old read context survives compaction without promoting candidate guesses."""

import json

from langchain_core.messages import AIMessage, ToolMessage

from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.harness.policies.agent_context import prepare_messages_with_diagnostics
from deeptrace.harness.policies.agent_context import message_tokens
from deeptrace.harness.token_budget import TokenBudgetConfig
from harness.test_agent_invariants import call, task
from harness.test_compact_research_context import exchange


def reading(text="If this flag is false, other tasks are NOT cancelled."):
    anchor = ReadEvidenceAnchor(
        evidence_id="source-1", version=1, content_hash="hash", start=0, end=len(text)
    )
    preview = json.dumps(
        {
            "evidence_id": anchor.evidence_id,
            "version": 1,
            "content_hash": anchor.content_hash,
            "historical": False,
            "passages": [{"ref": "n1", "start": 0, "end": len(text), "text": text}],
            "selection": {"body_length": len(text)},
        }
    )
    return anchor, [
        AIMessage(
            content="",
            tool_calls=[
                call("read_evidence", {"evidence_id": anchor.evidence_id}, "read")
            ],
        ),
        ToolMessage(
            content=json.dumps({"ok": True, "preview": preview}), tool_call_id="read"
        ),
    ]


def test_old_actual_read_is_retained_once_without_mutating_history():
    anchor, messages = reading()
    history = messages + [m for i in range(4) for m in exchange(i)]
    state = {"topic_input": task(), "messages": history, "read_anchors": [anchor]}
    view, _ = prepare_messages_with_diagnostics(state, (), TokenBudgetConfig())
    assert str(view).count("other tasks are NOT cancelled") == 1
    assert state["messages"] == history
    assert [m.tool_call_id for m in view if isinstance(m, ToolMessage)] == [
        "1",
        "2",
        "3",
    ]


def test_recent_read_is_not_duplicated_and_unanchored_preview_not_retained():
    anchor, messages = reading()
    view, _ = prepare_messages_with_diagnostics(
        {"topic_input": task(), "messages": messages, "read_anchors": [anchor]},
        (),
        TokenBudgetConfig(),
    )
    assert str(view).count("other tasks are NOT cancelled") == 1
    history = messages + [m for i in range(4) for m in exchange(i)]
    view, _ = prepare_messages_with_diagnostics(
        {"topic_input": task(), "messages": history}, (), TokenBudgetConfig()
    )
    assert "other tasks are NOT cancelled" not in str(view)


def test_retained_old_read_previews_fit_soft_budget_as_whole_passages():
    history = []
    anchors = []
    sentence = "条件成立时并不取消其他任务。"
    for index in range(3):
        body = f"来源{index}：" + sentence * 180
        anchor = ReadEvidenceAnchor(evidence_id=f"source-{index}", version=1,
                                    content_hash=f"hash-{index}", start=0, end=len(body))
        anchors.append(anchor)
        preview = json.dumps({
            "evidence_id": anchor.evidence_id, "version": 1,
            "content_hash": anchor.content_hash, "historical": False,
            "passages": [{"ref": f"n{index + 1}", "start": 0, "end": len(body), "text": body}],
            "selection": {"body_length": len(body)},
        }, ensure_ascii=False)
        assert len(preview) < 4000
        identity = f"read-{index}"
        history.extend([
            AIMessage(content="", tool_calls=[call("read_evidence", {"evidence_id": anchor.evidence_id}, identity)]),
            ToolMessage(content=json.dumps({"ok": True, "preview": preview}), tool_call_id=identity),
        ])
    history.extend(m for index in range(4) for m in exchange(index))
    state = {"topic_input": task(), "messages": history, "read_anchors": anchors}
    view, diagnostics = prepare_messages_with_diagnostics(state, (), TokenBudgetConfig())
    assert message_tokens(view) <= 6000
    assert "retained_read_context_omitted" in diagnostics
    assert state["messages"] == history
    content = str(view[1].content)
    for index in range(3):
        if f"来源{index}：" in content:
            assert f"来源{index}：" + sentence * 180 in content
    requested = [c["id"] for message in view for c in getattr(message, "tool_calls", [])]
    returned = [message.tool_call_id for message in view if isinstance(message, ToolMessage)]
    assert sorted(requested) == sorted(returned)
