"""Slim model views preserve durable sources and whole tool exchanges."""

import json

import pytest
from deeptrace.domain import EvidenceSupport, Finding, ResearchRequirement
from deeptrace.harness.policies.agent_context import (
    ContextLimitError,
    message_tokens,
    prepare_messages_with_diagnostics,
)
from deeptrace.harness.token_budget import TokenBudgetConfig
from langchain_core.messages import AIMessage, ToolMessage

from harness.test_agent_invariants import call, task


def exchange(index, text=None):
    identity = str(index)
    return [
        AIMessage(
            content="",
            tool_calls=[call("search_web", {"query": f"query-{index}"}, identity)],
        ),
        ToolMessage(
            content=json.dumps({"ok": True, "preview": text or f"BODY-{index}"}),
            tool_call_id=identity,
        ),
    ]


def test_only_recent_three_whole_exchanges_are_sent_without_mutating_history():
    history = [m for i in range(6) for m in exchange(i)]
    state = {"topic_input": task(), "messages": history}
    messages, _ = prepare_messages_with_diagnostics(state, (), TokenBudgetConfig())
    assert [m.tool_call_id for m in messages if isinstance(m, ToolMessage)] == [
        "3",
        "4",
        "5",
    ]
    assert "BODY-0" not in str(messages)
    assert state["messages"] == history and len(history) == 12


def test_candidate_claim_is_not_promoted_into_compact_context():
    note = Finding(
        id="research-1",
        claim="Candidate fact",
        confidence=0.8,
        evidence_ids=["source-1"],
        supports=[
            EvidenceSupport(
                evidence_id="source-1",
                version=1,
                content_hash="SECRET_HASH",
                start=0,
                end=18,
                quote="UNIQUE_RAW_SUPPORT",
            )
        ],
    )
    state = {"topic_input": task(), "research_findings": [note]}
    messages, _ = prepare_messages_with_diagnostics(state, (), TokenBudgetConfig())
    assert "Candidate fact" not in messages[1].content
    assert "UNIQUE_RAW_SUPPORT" not in messages[1].content
    assert "SECRET_HASH" not in messages[1].content
    assert state["research_findings"][0].supports[0].quote == "UNIQUE_RAW_SUPPORT"


def test_soft_oversized_latest_exchange_is_pinned_but_hard_limit_still_applies():
    state = {
        "topic_input": task(
            original_task="Keep Python 3.11 only", constraints=["Chinese answer"]
        ),
        "messages": exchange(1, "unique input " * 6000),
    }
    messages, diagnostics = prepare_messages_with_diagnostics(
        state, (), TokenBudgetConfig()
    )
    assert isinstance(messages[-1], ToolMessage)
    assert "soft_target_exceeded" in diagnostics
    assert "Keep Python 3.11 only" in str(messages)
    assert "Chinese answer" in str(messages)
    assert message_tokens(messages) > 8000
    with pytest.raises(ContextLimitError):
        prepare_messages_with_diagnostics(
            state, (), TokenBudgetConfig(context_tokens=1000)
        )


def test_assigned_requirement_and_remaining_budget_are_visible():
    source_task = task()
    source_task = source_task.model_copy(
        update={
            "requirements": [
                ResearchRequirement(id="r1", description="My assigned fact"),
                ResearchRequirement(id="r2", description="Other branch fact"),
            ],
            "target_requirement_ids": ["r1"],
        }
    )
    messages, _ = prepare_messages_with_diagnostics(
        {"topic_input": source_task},
        (),
        TokenBudgetConfig(),
        remaining_iterations=2,
    )
    content = messages[1].content
    assert "本分支负责" in content and "My assigned fact" in content
    assert "全局背景" in content and "Other branch fact" in content
    assert "剩余研究调用：2" in content


def test_host_progress_distinguishes_read_sources_and_quota_from_coverage():
    from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
    source_task = task().model_copy(update={"max_pages": 8})
    anchor = ReadEvidenceAnchor(evidence_id="source-1", version=1, content_hash="hash", start=0, end=5)
    messages, _ = prepare_messages_with_diagnostics({
        "topic_input": source_task, "pages_fetched": 2, "read_anchors": [anchor, anchor],
        "evidence_ids": ["source-1"],
    }, (), TokenBudgetConfig())
    content = str(messages[1].content)
    assert "抓页配额：2/8" in content
    assert "已实际读取 1 个来源" in content
    assert "已记录 0 条候选发现" in content
    assert "不代表需求已覆盖" in content
