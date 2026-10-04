from dataclasses import replace
from types import SimpleNamespace

import pytest
from strategies.fixtures import build_gateway_fixture

from deeptrace.domain import ConversationIntent
from deeptrace.harness.memory.lifecycle import _recall_memory


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["recall", "update", "consolidate"])
@pytest.mark.parametrize("missing", ["context", "store"])
async def test_memory_nodes_preserve_optional_runtime_boundaries(operation, missing):
    from deeptrace.harness.memory.lifecycle import (
        _consolidate_memory,
        _memory_update_node,
    )

    fixture = build_gateway_fixture()
    context = (
        None if missing == "context" else replace(fixture.context, memory_store=None)
    )
    state = {
        "turn": {"user_input": "请记住，用中文回答"},
        "conversation": {"evidence_ids": []},
    }
    nodes = {
        "recall": _recall_memory,
        "update": _memory_update_node,
        "consolidate": _consolidate_memory,
    }
    result = await nodes[operation](state, SimpleNamespace(context=context))
    if operation == "update":
        assert result["turn"]["response_outcome"].partial_reason == "memory_unavailable"
    elif operation == "recall":
        assert result == {"turn": state["turn"]}
    else:
        assert result == {}


class EvidenceReads:
    """Count reads while delegating to the real tenant-scoped store."""

    def __init__(self, store, batch_error=None):
        self.store = store
        self.batch_error = batch_error
        self.batches = []

    async def get_many(self, tenant, ids):
        self.batches.append((tenant, list(ids)))
        if self.batch_error is not None and len(self.batches) == 1:
            raise self.batch_error
        return await self.store.get_many(tenant, ids)

    async def read_body(self, tenant, identity):
        return await self.store.read_body(tenant, identity)


async def _ingest_source(
    fixture, *, tenant="workspace-1", url="source", body="content"
):
    from deeptrace.tools.evidence_store import EvidenceDraft

    return await fixture.evidence_store.ingest(
        tenant,
        EvidenceDraft(
            canonical_url=f"https://example.com/{url}",
            title=url,
            body=body,
            media_type="text/plain",
            source_quality=0.9,
            fetched_at=fixture.context.clock.now(),
        ),
    )


async def _consolidation_state(fixture, claims, *, allowed_ids=None):
    from deeptrace.domain import (
        EvidenceSupport,
        Finding,
        ResearchMode,
        ResearchOutcome,
        ResearchRequirement,
    )

    supports_by_id = {}
    for _, ids in claims:
        for identity in ids:
            if identity in supports_by_id:
                continue
            try:
                source = await fixture.evidence_store.get("workspace-1", identity)
                body = await fixture.evidence_store.read_body("workspace-1", identity)
                quote = body[:500]
                supports_by_id[identity] = EvidenceSupport(
                    evidence_id=identity,
                    version=source.version,
                    content_hash=source.content_hash,
                    start=0,
                    end=len(quote),
                    quote=quote,
                )
            except KeyError:
                supports_by_id[identity] = EvidenceSupport(
                    evidence_id=identity,
                    version=1,
                    content_hash="unknown",
                    start=0,
                    end=7,
                    quote="missing",
                )

    return {
        "turn": {
            "research_outcome": ResearchOutcome(
                evidence_contract_version=2,
                requirements=[
                    ResearchRequirement(id="r1", description="boundary fixture")
                ],
                mode=ResearchMode.WORKFLOW,
                evidence_ids=(
                    list(dict.fromkeys(source for _, ids in claims for source in ids))
                    if allowed_ids is None
                    else allowed_ids
                ),
                termination_reason="completed",
                executed_steps=1,
                findings=[
                    Finding(
                        id=f"finding-{i}",
                        claim=claim,
                        evidence_ids=ids,
                        confidence=0.9,
                        supports=[supports_by_id[identity] for identity in ids[:3]],
                    )
                    for i, (claim, ids) in enumerate(claims)
                ],
            )
        }
    }


@pytest.mark.asyncio
async def test_consolidation_batches_shared_sources_and_limits_findings():
    from datetime import timedelta

    from deeptrace.harness.memory.lifecycle import _consolidate_memory

    fixture = build_gateway_fixture()
    source = await _ingest_source(fixture)
    reads = EvidenceReads(fixture.evidence_store)
    state = await _consolidation_state(
        fixture, [(f"claim-{i}", [source.id]) for i in range(21)]
    )

    assert (
        await _consolidate_memory(
            state,
            SimpleNamespace(context=replace(fixture.context, evidence_store=reads)),
        )
        == {}
    )

    facts = await fixture.memory_store.list_namespace(
        ("workspace", "workspace-1", "facts")
    )
    assert {fact.content for fact in facts} == {f"claim-{i}" for i in range(20)}
    assert all(fact.source_evidence_ids == [source.id] for fact in facts)
    assert all(
        fact.expires_at == fixture.context.clock.now() + timedelta(days=30)
        for fact in facts
    )
    assert reads.batches == [("workspace-1", [source.id])]


@pytest.mark.asyncio
async def test_consolidation_missing_sources_do_not_discard_valid_siblings():
    from deeptrace.harness.memory.lifecycle import _consolidate_memory

    fixture = build_gateway_fixture()
    old = await _ingest_source(fixture)
    active = await _ingest_source(fixture, body="updated")
    foreign = await _ingest_source(fixture, tenant="other-workspace", body="foreign")
    reads = EvidenceReads(fixture.evidence_store)
    state = await _consolidation_state(
        fixture,
        [
            ("valid", [active.id]),
            ("missing", ["missing"]),
            ("foreign", [foreign.id]),
            ("superseded", [old.id]),
            ("partly missing", [active.id, "missing"]),
        ],
    )

    await _consolidate_memory(
        state, SimpleNamespace(context=replace(fixture.context, evidence_store=reads))
    )

    facts = await fixture.memory_store.list_namespace(
        ("workspace", "workspace-1", "facts")
    )
    assert [fact.content for fact in facts] == ["valid"]
    unique_ids = [active.id, "missing", foreign.id, old.id]
    assert reads.batches == [("workspace-1", unique_ids)] + [
        ("workspace-1", [item]) for item in unique_ids
    ]
    assert [name for name, _ in fixture.events.events].count("memory.degraded") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim", "ids", "allowed_ids"),
    [
        ("x" * 2001, ["source"], None),
        ("too many sources", [f"source-{i}" for i in range(21)], None),
        ("outside outcome", ["source"], []),
    ],
    ids=["content_limit", "source_limit", "outside_outcome"],
)
async def test_consolidation_invalid_candidates_do_not_read_evidence(
    claim, ids, allowed_ids
):
    from deeptrace.harness.memory.lifecycle import _consolidate_memory

    fixture = build_gateway_fixture()
    reads = EvidenceReads(fixture.evidence_store)
    await _consolidate_memory(
        await _consolidation_state(fixture, [(claim, ids)], allowed_ids=allowed_ids),
        SimpleNamespace(context=replace(fixture.context, evidence_store=reads)),
    )
    assert reads.batches == []
    assert (
        await fixture.memory_store.list_namespace(("workspace", "workspace-1", "facts"))
        == []
    )


@pytest.mark.asyncio
async def test_consolidation_storage_outage_does_not_retry_each_fact():
    from deeptrace.harness.memory.lifecycle import _consolidate_memory

    fixture = build_gateway_fixture()
    source = await _ingest_source(fixture)
    reads = EvidenceReads(fixture.evidence_store, batch_error=RuntimeError("offline"))
    state = await _consolidation_state(
        fixture, [("first", [source.id]), ("second", [source.id])]
    )

    await _consolidate_memory(
        state, SimpleNamespace(context=replace(fixture.context, evidence_store=reads))
    )

    assert reads.batches == [("workspace-1", [source.id])]
    assert (
        await fixture.memory_store.list_namespace(("workspace", "workspace-1", "facts"))
        == []
    )
    assert [name for name, _ in fixture.events.events].count("memory.degraded") == 1


@pytest.mark.asyncio
async def test_consolidation_empty_findings_do_not_read_evidence():
    from deeptrace.harness.memory.lifecycle import _consolidate_memory

    fixture = build_gateway_fixture()
    reads = EvidenceReads(fixture.evidence_store)
    assert (
        await _consolidate_memory(
            await _consolidation_state(fixture, []),
            SimpleNamespace(context=replace(fixture.context, evidence_store=reads)),
        )
        == {}
    )
    assert reads.batches == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["batch", "fallback"])
async def test_consolidation_propagates_evidence_read_cancellation(stage):
    import asyncio

    from deeptrace.harness.memory.lifecycle import _consolidate_memory

    fixture = build_gateway_fixture()
    source = await _ingest_source(fixture)

    class CancelledReads(EvidenceReads):
        async def get_many(self, tenant, ids):
            if self.batches:
                raise asyncio.CancelledError()
            return await super().get_many(tenant, ids)

    reads = CancelledReads(
        fixture.evidence_store,
        batch_error=asyncio.CancelledError()
        if stage == "batch"
        else KeyError("missing"),
    )
    with pytest.raises(asyncio.CancelledError):
        await _consolidate_memory(
            await _consolidation_state(fixture, [("claim", [source.id])]),
            SimpleNamespace(context=replace(fixture.context, evidence_store=reads)),
        )
    assert (
        await fixture.memory_store.list_namespace(("workspace", "workspace-1", "facts"))
        == []
    )


class RecordedIndex:
    def __init__(self):
        self.batches = []

    async def index(self, records):
        self.batches.append([record.model_copy(deep=True) for record in records])


@pytest.mark.asyncio
async def test_memory_consolidation_reports_completed_index_and_total_wall_time():
    from deeptrace.harness.memory.lifecycle import _consolidate_memory
    from deeptrace.harness.memory.store import InMemoryMemoryStore
    fixture = build_gateway_fixture()
    source = await _ingest_source(fixture)
    index = RecordedIndex()
    state = await _consolidation_state(fixture, [('supported fact', [source.id])])
    context = replace(fixture.context, memory_store=InMemoryMemoryStore(), memory_retriever=index)
    await _consolidate_memory(state, SimpleNamespace(context=context))
    events = dict(fixture.events.events)
    assert events['memory.index.completed']['records'] == len(index.batches[0]) == 1
    assert events['memory.index.completed']['status'] == 'completed'
    assert events['memory.consolidation.completed']['elapsed_seconds'] >= events['memory.index.completed']['elapsed_seconds'] >= 0


@pytest.mark.asyncio
async def test_memory_timing_does_not_report_cancelled_index_as_success():
    import asyncio
    from deeptrace.harness.memory.lifecycle import _consolidate_memory
    from deeptrace.harness.memory.store import InMemoryMemoryStore

    class CancelledIndex:
        async def index(self, records):
            raise asyncio.CancelledError()

    fixture = build_gateway_fixture()
    source = await _ingest_source(fixture)
    state = await _consolidation_state(fixture, [('supported fact', [source.id])])
    context = replace(fixture.context, memory_store=InMemoryMemoryStore(), memory_retriever=CancelledIndex())
    with pytest.raises(asyncio.CancelledError):
        await _consolidate_memory(state, SimpleNamespace(context=context))
    events = dict(fixture.events.events)
    assert events['memory.index.completed']['status'] == 'cancelled'
    assert events['memory.consolidation.completed']['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_consolidation_isolates_candidate_and_write_failures_before_indexing():
    from deeptrace.harness.memory.lifecycle import _consolidate_memory
    from deeptrace.harness.memory.store import InMemoryMemoryStore

    class FailOneStore(InMemoryMemoryStore):
        async def upsert(self, record, **kwargs):
            if record.content == "write fails":
                raise RuntimeError("one write failed")
            return await super().upsert(record, **kwargs)

    fixture = build_gateway_fixture()
    source = await _ingest_source(fixture)
    memory_store = FailOneStore()
    index = RecordedIndex()
    state = await _consolidation_state(
        fixture,
        [
            ("x" * 2001, [source.id]),
            ("write fails", [source.id]),
            ("valid sibling", [source.id]),
        ],
    )
    await _consolidate_memory(
        state,
        SimpleNamespace(
            context=replace(
                fixture.context, memory_store=memory_store, memory_retriever=index
            )
        ),
    )
    facts = await memory_store.list_namespace(("workspace", "workspace-1", "facts"))
    assert [fact.content for fact in facts] == ["valid sibling"]
    assert len(index.batches) == 1
    assert [record.id for record in index.batches[0]] == [facts[0].id]


@pytest.mark.asyncio
async def test_consolidation_replay_keeps_ttl_and_does_not_reactivate_deleted_fact():
    from datetime import timedelta

    from deeptrace.domain import MemoryStatus
    from deeptrace.harness.memory.forget import forget
    from deeptrace.harness.memory.lifecycle import _consolidate_memory

    fixture = build_gateway_fixture()
    source = await _ingest_source(fixture)
    index = RecordedIndex()
    context = replace(fixture.context, memory_retriever=index)
    state = await _consolidation_state(fixture, [("remember this fact", [source.id])])
    namespace = ("workspace", "workspace-1", "facts")
    await _consolidate_memory(state, SimpleNamespace(context=context))
    original = (await fixture.memory_store.list_namespace(namespace))[0]

    later_context = replace(
        context,
        clock=SimpleNamespace(now=lambda: original.updated_at + timedelta(days=1)),
    )
    await _consolidate_memory(state, SimpleNamespace(context=later_context))
    assert await fixture.memory_store.list_namespace(
        namespace, include_inactive=True
    ) == [original]

    await forget(fixture.memory_store, original)
    index.batches.clear()
    await _consolidate_memory(state, SimpleNamespace(context=later_context))
    assert await fixture.memory_store.list_namespace(namespace) == []
    history = await fixture.memory_store.list_namespace(
        namespace, include_inactive=True
    )
    assert len(history) == 1 and history[0].status is MemoryStatus.DELETED
    assert history[0].version == original.version
    assert index.batches == []


@pytest.mark.asyncio
async def test_explicit_save_evaluates_admission_once_and_persists(monkeypatch):
    from deeptrace.harness.memory import lifecycle
    from deeptrace.harness.memory.write import MemoryWritePolicy

    checks = []

    class TracedPolicy(MemoryWritePolicy):
        def can_store(self, record, *, source, supported_fact=False):
            checks.append(source)
            return super().can_store(
                record, source=source, supported_fact=supported_fact
            )

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
        def can_store(self, record, *, source, supported_fact=False):
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
        outcome = (await _consolidation_state(fixture, [(claim, [evidence.id])]))[
            "turn"
        ]["research_outcome"]
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
