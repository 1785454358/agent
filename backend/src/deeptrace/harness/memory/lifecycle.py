"""Session memory recall, explicit writes and post-research consolidation."""

from __future__ import annotations

import asyncio
import json
import logging
from time import perf_counter
from typing import Any

from langgraph.runtime import Runtime
from pydantic import ValidationError

from deeptrace.domain import (
    Evidence,
    EvidenceLifecycleStatus,
    Finding,
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
from deeptrace.tools.evidence_views import support_matches_record


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
    started = perf_counter()
    status = "failed"
    try:
        updates = await _consolidate_memory_impl(state, runtime)
        status = "completed"
        return updates
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    finally:
        await _memory_timing(context, "memory.consolidation.completed", started, status=status)


async def _consolidate_memory_impl(
    state: HarnessState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    context = runtime.context
    if context is None or context.memory_store is None:
        return {}
    memory_store = context.memory_store
    turn = state["turn"]
    outcome = turn.get("research_outcome")
    if (
        outcome is None
        or not outcome.findings
        or outcome.evidence_contract_version not in (2, 3)
    ):
        return {}
    now = context.clock.now()
    allowed_ids = set(outcome.evidence_ids)
    candidates: list[MemoryRecord] = []
    candidate_findings: list[Finding] = []
    for finding in outcome.findings[:20]:
        if (
            not finding.supports
            or not finding.evidence_ids
            or not set(finding.evidence_ids) <= allowed_ids
        ):
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
            candidate_findings.append(finding)
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
        sources = await _source_snapshot(context, source_ids)
    except Exception as exc:  # noqa: BLE001 - do not retry an unavailable evidence store
        await _degraded(context, "consolidation", exc)
        return {}
    policy = MemoryWritePolicy()
    stored_records: list[MemoryRecord] = []
    for record, finding in zip(candidates, candidate_findings, strict=True):
        if not await verify_finding_sources(
            finding, context, allowed_ids, _sources=sources
        ):
            continue
        try:
            stored = await remember(
                memory_store,
                record,
                policy,
                source="consolidation",
                supported_fact=True,
            )
            if stored.status is MemoryStatus.ACTIVE:
                stored_records.append(stored)
        except Exception as exc:  # noqa: BLE001 - optional consolidation preserves results
            await _degraded(context, "consolidation", exc)
    await _index_memory_best_effort(context, stored_records)
    return {}


async def _source_snapshot(
    context: HarnessContext, source_ids: list[str]
) -> dict[str, tuple[Evidence, str]]:
    """Batch metadata reads; only missing IDs trigger bounded per-ID fallback."""
    try:
        sources = await context.evidence_store.get_many(
            context.workspace_id, source_ids
        )
    except KeyError as exc:
        await _degraded(context, "consolidation", exc)
        sources = []
        for source_id in source_ids:
            try:
                found = await context.evidence_store.get_many(
                    context.workspace_id, [source_id]
                )
            except KeyError:
                continue
            sources.extend(found)
    snapshot = {}
    for source in sources:
        if source.status is not EvidenceLifecycleStatus.ACTIVE:
            continue
        try:
            body = await context.evidence_store.read_body(
                context.workspace_id, source.id
            )
        except Exception as exc:  # noqa: BLE001 - one bad source must not discard valid siblings
            await _degraded(context, "consolidation", exc)
            continue
        snapshot[source.id] = (source, body)
    return snapshot


async def verify_finding_sources(
    finding: Finding,
    context: HarnessContext,
    allowed_ids: set[str],
    *,
    _sources: dict[str, tuple[Evidence, str]] | None = None,
) -> bool:
    """Host-only admission check, with one shared snapshot per consolidation batch."""
    if (
        not finding.supports
        or not set(finding.evidence_ids) <= allowed_ids
        or set(finding.evidence_ids) != {s.evidence_id for s in finding.supports}
    ):
        return False
    try:
        sources = (
            _sources
            if _sources is not None
            else await _source_snapshot(context, finding.evidence_ids)
        )
        return all(
            s.evidence_id in sources
            and support_matches_record(s, *sources[s.evidence_id])
            for s in finding.supports
        )
    except Exception as exc:  # noqa: BLE001 - optional fact admission fails closed, cancellation propagates
        await _degraded(context, "consolidation", exc)
        return False


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
    started = perf_counter()
    status = "completed"
    try:
        await context.memory_retriever.index(records)
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception:
        status = "degraded"
        logging.getLogger(__name__).exception(
            "memory stored in authoritative store but Chroma indexing failed"
        )
    finally:
        await _memory_timing(
            context, "memory.index.completed", started, records=len(records), status=status
        )


async def _memory_timing(
    context: HarnessContext, event_type: str, started: float, **details: Any
) -> None:
    try:
        await context.event_sink.emit(
            event_type, {"elapsed_seconds": perf_counter() - started, **details}
        )
    except Exception:
        logging.getLogger(__name__).debug("Memory timing unavailable", exc_info=True)
