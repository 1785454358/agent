"""Executable policy tests for the six long-term memory questions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType
from deeptrace.harness.memory.forget import apply_lifecycle, forget
from deeptrace.harness.memory.recall import select_memories, should_recall
from deeptrace.harness.memory.store import InMemoryMemoryStore, namespace_for
from deeptrace.harness.memory.write import MemoryWritePolicy, remember

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def _record(**overrides: object) -> MemoryRecord:
    values: dict[str, object] = {
        "type": MemoryType.FACT,
        "namespace": ("workspace", "workspace-1", "facts"),
        "subject": "langgraph-checkpoint",
        "content": "LangGraph checkpoint 保存于 MySQL。",
        "source_evidence_ids": ["evidence-1"],
        "confidence": 0.9,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return MemoryRecord(**values)


# ── Q1: when to store ────────────────────────────────────────────────────────


def test_q1_when_to_store_user_request_and_sourced_findings() -> None:
    policy = MemoryWritePolicy()

    # explicit user request → store as preference, no evidence required
    assert (
        policy.can_store(
            _record(type=MemoryType.PREFERENCE, source_evidence_ids=[]),
            source="user_request",
        )
        is True
    )
    # research consolidation → facts require evidence support
    assert (
        policy.can_store(_record(type=MemoryType.FACT), source="consolidation")
        is True
    )
    assert (
        policy.can_store(
            _record(type=MemoryType.FACT, source_evidence_ids=[]),
            source="consolidation",
        )
        is False
    )
    # failed calls / transient intermediates are never stored
    assert (
        policy.can_store(_record(), source="failed_call") is False
    )
    assert (
        policy.can_store(_record(), source="intermediate") is False
    )


# ── Q2: what to store ────────────────────────────────────────────────────────


def test_q2_what_to_store_bounded_content_and_known_types() -> None:
    with pytest.raises(ValidationError):
        _record(content="")
    with pytest.raises(ValidationError):
        _record(content="x" * 4_000)
    with pytest.raises(ValidationError):
        _record(subject="")
    with pytest.raises(ValidationError):
        _record(source_evidence_ids=["evidence-1", "evidence-1"])
    with pytest.raises(ValidationError):
        _record(confidence=1.5)
    with pytest.raises(ValidationError):
        _record(importance=-0.1)
    assert _record(importance=0.75).importance == 0.75


# ── Q3: how to organize ──────────────────────────────────────────────────────


def test_q3_namespaces_are_scope_scoped_and_cross_tenant_is_blocked() -> None:
    assert namespace_for("user", "user-1", "preferences") == (
        "user",
        "user-1",
        "preferences",
    )
    assert namespace_for("workspace", "ws-1", "facts") == (
        "workspace",
        "ws-1",
        "facts",
    )

    store = InMemoryMemoryStore()
    import asyncio

    other_tenant = _record(
        namespace=("workspace", "ws-2", "facts"),
    )
    asyncio.run(store.put(other_tenant))

    # recall only sees the caller's own namespace
    found = asyncio.run(store.list_namespace(("workspace", "ws-1", "facts")))
    assert found == []


# ── Q4: when to recall ───────────────────────────────────────────────────────


def test_q4_when_to_recall_auto_triggers_and_followups_skip() -> None:
    from deeptrace.domain import ConversationIntent

    assert should_recall(ConversationIntent.RESEARCH, prior_evidence=False) is True
    assert (
        should_recall(ConversationIntent.INCREMENTAL_RESEARCH, prior_evidence=True)
        is True
    )
    assert should_recall(ConversationIntent.REPORT_REQUEST, prior_evidence=True) is True
    assert should_recall(ConversationIntent.CONVERSATION, prior_evidence=True) is False
    assert (
        should_recall(ConversationIntent.MEMORY_UPDATE, prior_evidence=False) is False
    )


def test_q4_recall_ranks_by_relevance_recency_and_confidence() -> None:
    records = [
        _record(
            subject="langgraph-checkpoint",
            content="checkpoint 在 MySQL",
            confidence=0.6,
            updated_at=NOW - timedelta(days=10),
        ),
        _record(
            subject="langgraph-checkpoint",
            content="checkpoint 在 MySQL，含 recovery 流程",
            confidence=0.95,
            updated_at=NOW - timedelta(days=1),
        ),
        _record(
            subject="tavily-quotes",
            content="Tavily 配额按月重置",
            confidence=0.9,
            updated_at=NOW,
        ),
        _record(
            subject="stale-entry",
            content="checkpoint 在 MySQL，含 recovery 流程（旧版）",
            status=MemoryStatus.SUPERSEDED,
        ),
    ]

    ranked = select_memories(
        records, query="checkpoint recovery 在哪里", now=NOW, limit=3
    )

    assert next(record.subject for record in ranked) == "langgraph-checkpoint"
    assert ranked[0].content.startswith("checkpoint 在 MySQL，含 recovery")
    assert all(record.subject != "stale-entry" for record in ranked)


# ── Q5: how to update ────────────────────────────────────────────────────────


def test_q5_updates_are_versioned_with_supersedes_chain() -> None:
    import asyncio

    store = InMemoryMemoryStore()
    policy = MemoryWritePolicy()

    first = asyncio.run(remember(store, _record(), policy))
    updated = asyncio.run(
        remember(
            store,
            _record(
                content="LangGraph checkpoint 已迁移到 MySQL Saver。",
                confidence=0.95,
            ),
            policy,
        )
    )

    assert updated.version == first.version + 1
    assert updated.supersedes == first.id
    assert updated.id != first.id
    # the superseded version remains queryable for the audit trail
    history = asyncio.run(
        store.list_namespace(("workspace", "workspace-1", "facts"), include_inactive=True)
    )
    old_version = next(
        record for record in history if record.version == first.version
    )
    assert old_version.status is MemoryStatus.SUPERSEDED
    # identical content is idempotent
    duplicate = asyncio.run(
        remember(
            store,
            _record(
                content="LangGraph checkpoint 已迁移到 MySQL Saver。",
                confidence=0.95,
            ),
            policy,
        )
    )
    assert duplicate.id == updated.id
    assert duplicate.version == updated.version


# ── Q6: how to forget ────────────────────────────────────────────────────────


def test_q6_forgetting_covers_expiry_staleness_and_deletion() -> None:
    import asyncio

    expired = _record(
        subject="expired-fact",
        expires_at=NOW - timedelta(days=1),
    )
    stale = _record(
        subject="old-fact",
        updated_at=NOW - timedelta(days=60),
    )
    fresh = _record(subject="fresh-fact")

    transitions = apply_lifecycle([expired, stale, fresh], now=NOW)

    assert transitions[expired.id] is MemoryStatus.EXPIRED
    assert transitions[stale.id] is MemoryStatus.STALE
    assert transitions[fresh.id] is None

    store = InMemoryMemoryStore()
    record = asyncio.run(store.put(_record()))
    deleted = asyncio.run(forget(store, record, mode="logical"))
    assert deleted.status is MemoryStatus.DELETED

    # deleted memories never surface in recall
    ranked = select_memories([deleted], query=record.subject, now=NOW, limit=5)
    assert ranked == []
