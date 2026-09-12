"""Recall policy: when long-term memory is consulted and how it is ranked."""

from __future__ import annotations

from datetime import datetime

from deeptrace.domain import ConversationIntent, MemoryRecord, MemoryStatus
from deeptrace.domain.memory import STALE_AFTER_DAYS


def should_recall(intent: ConversationIntent, *, prior_evidence: bool) -> bool:
    """Auto-trigger recall; ordinary follow-ups rely on short-term state only."""
    if intent is ConversationIntent.RESEARCH:
        return True
    if intent is ConversationIntent.INCREMENTAL_RESEARCH:
        return True
    if intent is ConversationIntent.REPORT_REQUEST:
        return True
    if intent is ConversationIntent.RESEARCH and prior_evidence:
        return True
    return False


def _tokens(text: str) -> set[str]:
    import re

    return {token.casefold() for token in re.findall(r"\w+", text or "")}


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
        if record.status is not MemoryStatus.ACTIVE:
            continue
        if record.expires_at is not None and record.expires_at <= now:
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
    return [record for _score, record in candidates[:limit]]


def is_stale(record: MemoryRecord, *, now: datetime) -> bool:
    age_days = (now - record.updated_at).total_seconds() / 86_400
    return age_days > STALE_AFTER_DAYS
