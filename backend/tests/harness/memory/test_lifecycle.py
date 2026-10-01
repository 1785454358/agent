from dataclasses import replace
from types import SimpleNamespace

import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ConversationIntent
from deeptrace.harness.memory.lifecycle import _recall_memory


@pytest.mark.asyncio
async def test_explicit_save_evaluates_admission_once_and_persists(monkeypatch):
    from deeptrace.harness.memory import lifecycle
    from deeptrace.harness.memory.write import MemoryWritePolicy

    checks = []

    class TracedPolicy(MemoryWritePolicy):
        def can_store(self, record, *, source):
            checks.append(source)
            return super().can_store(record, source=source)

    monkeypatch.setattr(lifecycle, "MemoryWritePolicy", TracedPolicy)
    fixture = build_gateway_fixture()
    result = await lifecycle._memory_update_node(
        {"turn": {"user_input": "请记住，以后用中文回答"}},
        SimpleNamespace(context=fixture.context),
    )
    assert result["turn"]["response_outcome"].partial_reason == "memory_updated"
    records = await fixture.memory_store.list_namespace(
        ("user", "user-1", "preferences")
    )
    assert [record.content for record in records] == ["以后用中文回答"]
    assert checks == ["user_request"]


@pytest.mark.asyncio
async def test_explicit_admission_rejection_does_not_persist(monkeypatch):
    from deeptrace.harness.memory import lifecycle
    from deeptrace.harness.memory.write import MemoryWritePolicy

    class DeniedPolicy(MemoryWritePolicy):
        def can_store(self, record, *, source):
            return False

    monkeypatch.setattr(lifecycle, "MemoryWritePolicy", DeniedPolicy)
    fixture = build_gateway_fixture()
    result = await lifecycle._memory_update_node(
        {"turn": {"user_input": "请记住，以后用中文回答"}},
        SimpleNamespace(context=fixture.context),
    )
    assert result["turn"]["response_outcome"].partial_reason == "memory_rejected"
    assert (
        await fixture.memory_store.list_namespace(("user", "user-1", "preferences"))
        == []
    )


@pytest.mark.asyncio
async def test_explicit_save_survives_index_failure():
    from deeptrace.harness.memory.lifecycle import _memory_update_node

    class FailedIndex:
        async def index(self, records):
            raise RuntimeError("index unavailable")

    fixture = build_gateway_fixture()
    result = await _memory_update_node(
        {"turn": {"user_input": "请记住，以后用中文回答"}},
        SimpleNamespace(
            context=replace(fixture.context, memory_retriever=FailedIndex())
        ),
    )
    assert result["turn"]["response_outcome"].partial_reason == "memory_updated"
    assert (
        len(
            await fixture.memory_store.list_namespace(("user", "user-1", "preferences"))
        )
        == 1
    )


@pytest.mark.asyncio
async def test_explicit_save_propagates_store_cancellation():
    import asyncio

    from deeptrace.harness.memory.lifecycle import _memory_update_node
    from deeptrace.harness.memory.store import InMemoryMemoryStore

    class CancelledStore(InMemoryMemoryStore):
        async def upsert(self, record, **kwargs):
            raise asyncio.CancelledError()

    fixture = build_gateway_fixture()
    with pytest.raises(asyncio.CancelledError):
        await _memory_update_node(
            {"turn": {"user_input": "请记住，以后用中文回答"}},
            SimpleNamespace(
                context=replace(fixture.context, memory_store=CancelledStore())
            ),
        )


@pytest.mark.asyncio
async def test_optional_recall_failure_degrades_without_losing_task():
    class BrokenRetriever:
        async def recall(self, **kwargs):
            raise RuntimeError("unavailable")

    fixture = build_gateway_fixture()
    runtime = SimpleNamespace(
        context=replace(fixture.context, memory_retriever=BrokenRetriever())
    )
    result = await _recall_memory(
        {
            "turn": {"intent": ConversationIntent.RESEARCH, "user_input": "original"},
            "conversation": {"evidence_ids": []},
        },
        runtime,
    )
    assert result["turn"]["user_input"] == "original"
    assert result["turn"]["recalled_memories"] == []
    assert any(name == "memory.degraded" for name, _ in fixture.events.events)


@pytest.mark.asyncio
async def test_explicit_preferences_update_the_same_language_slot():
    from deeptrace.harness.memory.lifecycle import _memory_update_node

    fixture = build_gateway_fixture()
    runtime = SimpleNamespace(context=fixture.context)
    for text in ["请记住，以后用中文回答", "请记住，以后用英文回答"]:
        await _memory_update_node({"turn": {"user_input": text}}, runtime)
    records = await fixture.memory_store.list_namespace(
        ("user", "user-1", "preferences")
    )
    assert len(records) == 1
    assert records[0].subject == "response.language"
    assert "英文" in records[0].content and records[0].version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("storage offline"), ValueError("memory_write_rejected")]
)
async def test_explicit_memory_write_reports_store_failure(error):
    from deeptrace.harness.memory.lifecycle import _memory_update_node
    from deeptrace.harness.memory.store import InMemoryMemoryStore

    class BrokenStore(InMemoryMemoryStore):
        async def upsert(self, record, **kwargs):
            raise error

    fixture = build_gateway_fixture()
    runtime = SimpleNamespace(
        context=replace(fixture.context, memory_store=BrokenStore())
    )
    result = await _memory_update_node(
        {"turn": {"user_input": "请记住，以后用中文回答"}}, runtime
    )
    assert result["turn"]["response_outcome"].partial_reason == "memory_unavailable"


@pytest.mark.asyncio
async def test_consolidation_rejects_fabricated_evidence_ids():
    from deeptrace.domain import Finding, ResearchMode, ResearchOutcome
    from deeptrace.harness.memory.lifecycle import _consolidate_memory

    fixture = build_gateway_fixture()
    outcome = ResearchOutcome(
        mode=ResearchMode.WORKFLOW,
        evidence_ids=["fabricated"],
        termination_reason="completed",
        executed_steps=1,
        findings=[
            Finding(
                id="finding-1",
                claim="a claim",
                evidence_ids=["fabricated"],
                confidence=0.9,
            )
        ],
    )
    await _consolidate_memory(
        {"turn": {"research_outcome": outcome}},
        SimpleNamespace(context=fixture.context),
    )
    assert (
        await fixture.memory_store.list_namespace(("workspace", "workspace-1", "facts"))
        == []
    )


@pytest.mark.asyncio
async def test_consolidation_preserves_distinct_facts_and_degrades_on_store_failure():
    from deeptrace.domain import Finding, ResearchMode, ResearchOutcome
    from deeptrace.harness.memory.lifecycle import _consolidate_memory
    from deeptrace.harness.memory.store import InMemoryMemoryStore
    from deeptrace.tools.evidence_store import EvidenceDraft

    fixture = build_gateway_fixture()
    now = fixture.context.clock.now()
    evidence = await fixture.evidence_store.ingest(
        "workspace-1",
        EvidenceDraft(
            canonical_url="https://example.com/source",
            title="source",
            body="reliable content",
            media_type="text/plain",
            source_quality=0.9,
            fetched_at=now,
        ),
    )
    for claim in ["checkpoint 保存图状态", "预算在工具执行前预留"]:
        outcome = ResearchOutcome(
            mode=ResearchMode.WORKFLOW,
            evidence_ids=[evidence.id],
            termination_reason="completed",
            executed_steps=1,
            findings=[
                Finding(
                    id="finding-1",
                    claim=claim,
                    evidence_ids=[evidence.id],
                    confidence=0.9,
                )
            ],
        )
        await _consolidate_memory(
            {"turn": {"research_outcome": outcome}},
            SimpleNamespace(context=fixture.context),
        )
    records = await fixture.memory_store.list_namespace(
        ("workspace", "workspace-1", "facts")
    )
    assert len(records) == 2 and all(r.expires_at is not None for r in records)

    class BrokenStore(InMemoryMemoryStore):
        async def upsert(self, record, **kwargs):
            raise RuntimeError("store offline")

    runtime = SimpleNamespace(
        context=replace(fixture.context, memory_store=BrokenStore())
    )
    assert (
        await _consolidate_memory({"turn": {"research_outcome": outcome}}, runtime)
        == {}
    )
    assert any(name == "memory.degraded" for name, _ in fixture.events.events)


@pytest.mark.asyncio
async def test_recall_obeys_token_budget_and_preserves_provenance():
    import json

    from deeptrace.domain import MemoryRecord, MemoryType
    from deeptrace.harness.token_budget import count_tokens

    fixture = build_gateway_fixture()
    now = fixture.context.clock.now()
    for i in range(4):
        await fixture.memory_store.put(
            MemoryRecord(
                type=MemoryType.PREFERENCE,
                namespace=("user", "user-1", "preferences"),
                subject=f"preference-{i}",
                content="Prefer short answers. " * 50,
                created_at=now,
                updated_at=now,
            )
        )
    runtime = SimpleNamespace(
        context=replace(fixture.context, memory_context_tokens=220)
    )
    result = await _recall_memory(
        {
            "turn": {"intent": ConversationIntent.RESEARCH, "user_input": "checkpoint"},
            "conversation": {"evidence_ids": []},
        },
        runtime,
    )
    memories = result["turn"]["recalled_memories"]
    assert memories
    assert count_tokens(json.dumps(memories, ensure_ascii=False)) <= 220
    assert all("id" in m and "version" in m and "updated_at" in m for m in memories)
