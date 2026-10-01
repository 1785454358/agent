"""Recall policy: when long-term memory is consulted and how it is ranked."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from deeptrace.domain import ConversationIntent, MemoryRecord, MemoryStatus
from deeptrace.domain.memory import STALE_AFTER_DAYS


def should_recall(intent: ConversationIntent, *, prior_evidence: bool) -> bool:
    """Auto-trigger recall; ordinary follow-ups rely on short-term state only."""
    if intent is ConversationIntent.RESEARCH:
        return True
    if intent is ConversationIntent.INCREMENTAL_RESEARCH:
        return True
    return intent is ConversationIntent.REPORT_REQUEST


def _tokens(text: str) -> set[str]:
    tokens = {token.casefold() for token in re.findall(r"[a-zA-Z0-9_]+", text or "")}
    for span in re.findall(r"[\u4e00-\u9fff]+", text or ""):
        tokens.update(span[i : i + 2] for i in range(len(span) - 1))
    return tokens


def eligible_memory(record: MemoryRecord, *, now: datetime) -> bool:
    return record.status is MemoryStatus.ACTIVE and (
        record.expires_at is None or record.expires_at > now
    )


def memory_context_line(memory: Mapping[str, Any]) -> str:
    """Keep provenance visible in prompts, accepting legacy checkpoint views."""
    content = memory["content"]
    if not memory.get("id"):
        return content
    sources = ",".join(memory.get("source_evidence_ids") or []) or "用户显式偏好"
    return (
        f"历史记忆（当前请求优先，事实需核验）[{memory['id']} v{memory['version']}; "
        f"updated={memory['updated_at']}; sources={sources}] {content}"
    )


def select_memories(
    records: list[MemoryRecord],
    *,
    query: str,
    now: datetime,
    limit: int = 5,
) -> list[MemoryRecord]:
    """Deterministic ranking: status gate, keyword overlap, recency, confidence."""
    query_tokens = _tokens(query)
    candidates: list[tuple[float, MemoryRecord]] = []
    for record in records:
        if not eligible_memory(record, now=now):
            continue
        subject_tokens = _tokens(record.subject)
        content_tokens = _tokens(record.content)
        overlap = len(query_tokens & subject_tokens) * 2.0 + len(
            query_tokens & content_tokens
        )
        age_days = max(0.0, (now - record.updated_at).total_seconds() / 86_400)
        recency = 1.0 / (1.0 + age_days)
        score = overlap * 10.0 + recency * 5.0 + record.confidence * 3.0
        if overlap <= 0 and record.type.value != "preference":
            continue
        candidates.append((score, record))

    candidates.sort(key=lambda item: (-item[0], item[1].identity()))
    return [record for _score, record in candidates[: max(0, limit)]]


def is_stale(record: MemoryRecord, *, now: datetime) -> bool:
    age_days = (now - record.updated_at).total_seconds() / 86_400
    return age_days > STALE_AFTER_DAYS
