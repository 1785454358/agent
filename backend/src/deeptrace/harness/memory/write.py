"""Write policy: when and what may enter long-term memory."""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from deeptrace.domain import MemoryRecord, MemoryStatus, MemoryType

_ALLOWED_SOURCES = {"user_request", "consolidation", "repeated_preference"}


class MemoryWriteRejected(ValueError):
    """Admission rejected the write, rather than storage being unavailable."""


class MemoryWritePolicy:
    """Gate every long-term write; one-off or unsupported content is rejected."""

    def can_store(self, record: MemoryRecord, *, source: str) -> bool:
        if source not in _ALLOWED_SOURCES:
            return False
        if (
            not isinstance(record, MemoryRecord)
            or record.status is not MemoryStatus.ACTIVE
        ):
            return False
        if record.type is MemoryType.FACT:
            # facts require source evidence support
            return bool(record.source_evidence_ids)
        if record.type is MemoryType.PREFERENCE:
            return source in {"user_request", "repeated_preference"}
        if record.type is MemoryType.EVIDENCE:
            return bool(record.source_evidence_ids)
        if record.type is MemoryType.EPISODE:
            return source == "consolidation"
        return False


def memory_subject(content: str, *, preference: bool = False) -> str:
    """Stable slots for known preferences; unknown facts remain separate items."""
    text = content.strip()
    if preference:
        if re.search(r"(中文|英文|英语|汉语)", text) and re.search(
            r"(用|使用|回答|回复|输出)", text
        ):
            return "response.language"
        if re.search(r"(简洁|简短|详细|详尽)", text) and re.search(
            r"(回答|回复|输出|内容|解释)", text
        ):
            return "response.detail"
        if re.search(r"(表格|markdown|列表)", text, re.IGNORECASE) and re.search(
            r"(用|使用|格式|输出)", text
        ):
            return "response.format"
    normalized = " ".join(text.casefold().split())
    return "item-" + hashlib.sha256(normalized.encode()).hexdigest()[:32]


async def remember(
    store,
    record: MemoryRecord,
    policy: MemoryWritePolicy,
    *,
    source: str = "consolidation",
) -> MemoryRecord:
    """Admission, retention and atomic versioning are one write boundary."""
    if not policy.can_store(record, source=source):
        raise MemoryWriteRejected("memory_write_rejected")
    if record.type is MemoryType.FACT and record.expires_at is None:
        record = record.model_copy(
            update={"expires_at": record.updated_at + timedelta(days=30)}
        )
    return await store.upsert(record, allow_reactivate=source == "user_request")
