"""Evidence Store 使用的确定性标识符。"""

import hashlib


def stable_id(prefix: str, *parts: object) -> str:
    """用身份字段生成跨运行稳定且带命名空间的短 ID。"""
    payload = "\x1f".join(str(part).strip() for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def source_id(doc_id: str) -> str:
    return stable_id("source", doc_id)


def evidence_id(
    source_id: str,
    note_id: str,
    quote_hash: str,
    char_start: int | None,
) -> str:
    return stable_id("evidence", source_id, note_id, quote_hash, char_start)


def claim_id(task_id: str, section_id: str, text: str) -> str:
    return stable_id("claim", task_id, section_id, text)

