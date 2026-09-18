"""Session memory recall, explicit writes and post-research consolidation."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.runtime import Runtime

from deeptrace.domain import MemoryRecord, MemoryType, ResponseMode, ResponseOutcome
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.memory.recall import select_memories, should_recall
from deeptrace.harness.memory.write import MemoryWritePolicy, remember
from deeptrace.harness.state import HarnessState


def _extract_memory_content(user_input: str) -> str:
    text = (user_input or "").strip()
    for prefix in (
        "请帮我记住，",
        "请帮我记住",
        "请记住，",
        "请记住",
        "帮我记住，",
        "帮我记住",
        "记住，",
        "记住我",
        "记住",
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip(" ，,。:：")
            break
    if not text:
        text = user_input.strip()
    return text[:2_000]


async def _recall_memory(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    turn = dict(state["turn"])
    context = runtime.context
    memory_store = context.memory_store if context is not None else None
    if memory_store is None:
        return {"turn": turn}
    prior_evidence = bool(state["conversation"]["evidence_ids"])
    if not should_recall(turn["intent"], prior_evidence=prior_evidence):
        return {"turn": turn}
    now = runtime.context.clock.now()
    records: list[Any] = []
    namespaces = [
        ("user", runtime.context.user_id, "preferences"),
        ("workspace", runtime.context.workspace_id, "facts"),
    ]
    try:
        retriever = runtime.context.memory_retriever
        if retriever is not None:
            ranked = await retriever.recall(
                namespaces=namespaces,
                memory_types={MemoryType.PREFERENCE, MemoryType.FACT},
                query=turn["user_input"],
                now=now,
                limit=runtime.context.memory_recall_limit,
            )
        else:
            records = await memory_store.list_eligible(
                namespaces=namespaces,
                memory_types={MemoryType.PREFERENCE, MemoryType.FACT},
                now=now,
            )
            ranked = select_memories(
                records,
                query=turn["user_input"],
                now=now,
                limit=runtime.context.memory_recall_limit,
            )
    except Exception:
        logging.getLogger(__name__).exception("Optional memory recall unavailable")
        ranked = []
        try:
            await context.event_sink.emit("memory.degraded", {"stage": "recall"})
        except Exception:
            logging.getLogger(__name__).warning(
                "Memory degradation event unavailable", exc_info=True
            )
    turn["recalled_memory_ids"] = [record.id for record in ranked]
    turn["recalled_memories"] = [
        {
            "type": record.type.value,
            "subject": record.subject[:200],
            "content": record.content[:500],
        }
        for record in ranked
    ]
    return {"turn": turn}


async def _memory_update_node(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    turn = dict(state["turn"])
    content = _extract_memory_content(turn["user_input"])
    context = runtime.context
    memory_store = context.memory_store if context is not None else None
    if memory_store is None:
        turn["response_outcome"] = ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="记忆功能当前不可用，未能保存。",
            citations=[],
            cited_evidence_ids=[],
            partial_reason="memory_unavailable",
        )
        return {"turn": turn}
    now = runtime.context.clock.now()
    record = MemoryRecord(
        type=MemoryType.PREFERENCE,
        namespace=("user", runtime.context.user_id, "preferences"),
        subject=content[:200],
        content=content,
        confidence=1.0,
        created_at=now,
        updated_at=now,
    )
    policy = MemoryWritePolicy()
    if not policy.can_store(record, source="user_request"):
        turn["response_outcome"] = ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="这条内容不符合保存策略，未能记住。",
            citations=[],
            cited_evidence_ids=[],
            partial_reason="memory_rejected",
        )
        return {"turn": turn}
    stored = await remember(memory_store, record, policy)
    await _index_memory_best_effort(runtime.context, [stored])
    turn["response_outcome"] = ResponseOutcome(
        response_mode=ResponseMode.ANSWER,
        content=f"已记住：{content}",
        citations=[],
        cited_evidence_ids=[],
        partial_reason="memory_updated",
    )
    return {"turn": turn}


async def _consolidate_memory(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    context = runtime.context
    memory_store = context.memory_store if context is not None else None
    if memory_store is None:
        return {}
    turn = state["turn"]
    outcome = turn.get("research_outcome")
    if outcome is None or not outcome.findings:
        return {}
    now = runtime.context.clock.now()
    policy = MemoryWritePolicy()
    stored_records: list[MemoryRecord] = []
    for finding in outcome.findings[:20]:
        record = MemoryRecord(
            type=MemoryType.FACT,
            namespace=("workspace", runtime.context.workspace_id, "facts"),
            subject=finding.id[:200],
            content=finding.claim,
            source_evidence_ids=list(finding.evidence_ids),
            confidence=finding.confidence,
            created_at=now,
            updated_at=now,
        )
        if policy.can_store(record, source="consolidation"):
            stored = await remember(memory_store, record, policy)
            stored_records.append(stored)
    await _index_memory_best_effort(runtime.context, stored_records)
    return {}


async def _index_memory_best_effort(
    context: HarnessContext, records: list[MemoryRecord]
) -> None:
    if context.memory_retriever is None or not records:
        return
    try:
        await context.memory_retriever.index(records)
    except Exception:
        logging.getLogger(__name__).exception(
            "memory stored in authoritative store but Chroma indexing failed"
        )
