"""Session memory recall, explicit writes and post-research consolidation."""

from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.runtime import Runtime
from pydantic import ValidationError

from deeptrace.domain import (
    EvidenceLifecycleStatus,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    ResponseMode,
    ResponseOutcome,
)
from deeptrace.domain.memory import RecalledMemory
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.memory.recall import (
    eligible_memory,
    select_memories,
    should_recall,
)
from deeptrace.harness.memory.write import (
    MemoryWritePolicy,
    MemoryWriteRejected,
    memory_subject,
    remember,
)
from deeptrace.harness.state import HarnessState
from deeptrace.harness.token_budget import count_tokens


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
    if context is None or context.memory_store is None:
        return {"turn": turn}
    memory_store = context.memory_store
    prior_evidence = bool(state["conversation"]["evidence_ids"])
    if not should_recall(turn["intent"], prior_evidence=prior_evidence):
        return {"turn": turn}
    now = context.clock.now()
    ranked: list[MemoryRecord] = []
    preference_namespace = ("user", context.user_id, "preferences")
    fact_namespace = ("workspace", context.workspace_id, "facts")
    try:
        preferences = await memory_store.list_eligible(
            namespaces=[preference_namespace],
            memory_types={MemoryType.PREFERENCE},
            now=now,
        )
        preferences = [
            r
            for r in preferences
            if r.namespace == preference_namespace and r.type is MemoryType.PREFERENCE
        ]
        ranked = select_memories(
            preferences,
            query=turn["user_input"],
            now=now,
            limit=context.memory_recall_limit,
        )
        remaining = max(0, context.memory_recall_limit - len(ranked))
        retriever = context.memory_retriever
        if retriever is not None and remaining:
            facts = await retriever.recall(
                namespaces=[fact_namespace],
                memory_types={MemoryType.FACT},
                query=turn["user_input"],
                now=now,
                limit=remaining,
            )
        elif remaining:
            records = await memory_store.list_eligible(
                namespaces=[fact_namespace],
                memory_types={MemoryType.FACT},
                now=now,
            )
            facts = select_memories(
                records,
                query=turn["user_input"],
                now=now,
                limit=remaining,
            )
        else:
            facts = []
        ranked.extend(
            r
            for r in facts
            if r.namespace == fact_namespace
            and r.type is MemoryType.FACT
            and eligible_memory(r, now=now)
        )
    except Exception as exc:  # noqa: BLE001 - optional recall must not fail research
        await _degraded(context, "recall", exc)
    views: list[RecalledMemory] = []
    for record in ranked[: max(0, context.memory_recall_limit)]:
        view: RecalledMemory = {
            "id": record.id,
            "version": record.version,
            "type": record.type.value,
            "subject": record.subject,
            "content": record.content[:500],
            "source_evidence_ids": list(record.source_evidence_ids),
            "confidence": record.confidence,
            "updated_at": record.updated_at.isoformat(),
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        }
        if (
            count_tokens(json.dumps(views + [view], ensure_ascii=False))
            <= context.memory_context_tokens
        ):
            views.append(view)
    turn["recalled_memory_ids"] = [view["id"] for view in views]
    turn["recalled_memories"] = views
    return {"turn": turn}


async def _memory_update_node(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    turn = dict(state["turn"])
    content = _extract_memory_content(turn["user_input"])
    context = runtime.context
    if context is None or context.memory_store is None:
        turn["response_outcome"] = ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="记忆功能当前不可用，未能保存。",
            citations=[],
            cited_evidence_ids=[],
            partial_reason="memory_unavailable",
        )
        return {"turn": turn}
    memory_store = context.memory_store
    now = context.clock.now()
    record = MemoryRecord(
        type=MemoryType.PREFERENCE,
        namespace=("user", context.user_id, "preferences"),
        subject=memory_subject(content, preference=True),
        content=content,
        confidence=1.0,
        created_at=now,
        updated_at=now,
    )
    policy = MemoryWritePolicy()
    try:
        stored = await remember(memory_store, record, policy, source="user_request")
    except MemoryWriteRejected:
        turn["response_outcome"] = ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="这条内容不符合保存策略，未能记住。",
            citations=[],
            cited_evidence_ids=[],
            partial_reason="memory_rejected",
        )
        return {"turn": turn}
    except Exception as exc:  # noqa: BLE001 - report explicit persistence failure
        await _degraded(context, "explicit_write", exc)
        turn["response_outcome"] = ResponseOutcome(
            response_mode=ResponseMode.ANSWER,
            content="记忆保存失败，未能记住。",
            citations=[],
            cited_evidence_ids=[],
            partial_reason="memory_unavailable",
        )
        return {"turn": turn}
    await _index_memory_best_effort(context, [stored])
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
    if context is None or context.memory_store is None:
        return {}
    memory_store = context.memory_store
    turn = state["turn"]
    outcome = turn.get("research_outcome")
    if outcome is None or not outcome.findings:
        return {}
    now = context.clock.now()
    allowed_ids = set(outcome.evidence_ids)
    candidates: list[MemoryRecord] = []
    for finding in outcome.findings[:20]:
        if not finding.evidence_ids or not set(finding.evidence_ids) <= allowed_ids:
            continue
        try:
            candidates.append(
                MemoryRecord(
                    type=MemoryType.FACT,
                    namespace=("workspace", context.workspace_id, "facts"),
                    subject=memory_subject(finding.claim),
                    content=finding.claim,
                    source_evidence_ids=list(finding.evidence_ids),
                    confidence=finding.confidence,
                    created_at=now,
                    updated_at=now,
                )
            )
        except ValidationError as exc:
            await _degraded(context, "consolidation", exc)
    if not candidates:
        return {}
    source_ids = list(
        dict.fromkeys(
            source for record in candidates for source in record.source_evidence_ids
        )
    )
    try:
        active_ids = await _active_evidence_ids(context, source_ids)
    except Exception as exc:  # noqa: BLE001 - do not retry an unavailable evidence store
        await _degraded(context, "consolidation", exc)
        return {}
    policy = MemoryWritePolicy()
    stored_records: list[MemoryRecord] = []
    for record in candidates:
        if not set(record.source_evidence_ids) <= active_ids:
            continue
        try:
            stored = await remember(
                memory_store, record, policy, source="consolidation"
            )
            if stored.status is MemoryStatus.ACTIVE:
                stored_records.append(stored)
        except Exception as exc:  # noqa: BLE001 - optional consolidation preserves results
            await _degraded(context, "consolidation", exc)
    await _index_memory_best_effort(context, stored_records)
    return {}


async def _active_evidence_ids(
    context: HarnessContext, source_ids: list[str]
) -> set[str]:
    """Batch metadata reads; only missing IDs trigger bounded per-ID fallback."""
    try:
        sources = await context.evidence_store.get_many(
            context.workspace_id, source_ids
        )
    except KeyError as exc:
        await _degraded(context, "consolidation", exc)
        active_ids: set[str] = set()
        for source_id in source_ids:
            try:
                sources = await context.evidence_store.get_many(
                    context.workspace_id, [source_id]
                )
            except KeyError:
                continue
            active_ids.update(
                source.id
                for source in sources
                if source.status is EvidenceLifecycleStatus.ACTIVE
            )
        return active_ids
    return {
        source.id
        for source in sources
        if source.status is EvidenceLifecycleStatus.ACTIVE
    }


async def _degraded(context: HarnessContext, stage: str, error: Exception) -> None:
    logging.getLogger(__name__).warning(
        "Optional memory stage unavailable: %s",
        stage,
        exc_info=(type(error), error, error.__traceback__),
    )
    try:
        await context.event_sink.emit("memory.degraded", {"stage": stage})
    except Exception:
        logging.getLogger(__name__).warning(
            "Memory degradation event unavailable", exc_info=True
        )


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
