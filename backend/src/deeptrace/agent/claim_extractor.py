"""原子 Claim 抽取、校正与确定性降级。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import json_repair
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from deeptrace.agent._shared import add_usage, message_text, message_usage
from deeptrace.evidence import claim_id
from deeptrace.models import (
    Claim,
    ClaimImportance,
    ClaimKind,
    Evidence,
    NumericDetail,
    ResearchNote,
    ResearchTask,
    ResearchTimeRange,
    TokenUsage,
)
from deeptrace.prompts.claim_extractor import build_claim_extractor_messages


class ClaimDraft(BaseModel):
    """模型输出的 Claim 草稿，ID 由本地生成。"""

    text: str = Field(min_length=1)
    kind: ClaimKind
    importance: ClaimImportance
    event_start_date: date | None = None
    event_end_date: date | None = None
    numeric: NumericDetail | None = None
    evidence_ids: list[str] = Field(min_length=1)


class ClaimExtractorOutput(BaseModel):
    claims: list[ClaimDraft] = Field(default_factory=list)


def parse_claim_output(raw: str) -> ClaimExtractorOutput:
    """修复并校验 Provider 返回的 Claim JSON。"""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Claim Extractor 未返回 JSON 对象")
    try:
        payload = json_repair.loads(raw[start : end + 1])
        return ClaimExtractorOutput.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"Claim Extractor JSON 无法校验：{exc}") from exc


def materialize_claims(
    drafts: Sequence[ClaimDraft],
    evidence: Mapping[str, Evidence],
    task: ResearchTask,
    time_range: ResearchTimeRange | None,
) -> list[Claim]:
    """过滤不可定位引用并生成稳定 Claim ID。"""
    del time_range  # 越界主张交给确定性 Verifier 分类，不能在此丢弃。
    result: list[Claim] = []
    seen: set[str] = set()
    for draft in drafts:
        valid_ids = list(
            dict.fromkeys(
                item_id
                for item_id in draft.evidence_ids
                if item_id in evidence
                and evidence[item_id].location_status == "exact"
            )
        )
        identity = claim_id(task.task_id, task.section_id, draft.text)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(
            Claim(
                claim_id=identity,
                task_id=task.task_id,
                section_id=task.section_id,
                text=draft.text.strip(),
                kind=draft.kind,
                importance=draft.importance,
                event_start=draft.event_start_date,
                event_end=draft.event_end_date,
                numeric=draft.numeric,
                evidence_ids=valid_ids,
            )
        )
    return result


def fallback_claims(
    notes: Sequence[ResearchNote],
    evidence: Sequence[Evidence],
) -> list[Claim]:
    """用笔记关键点生成 supporting Claim，避免降级内容冒充已验证事实。"""
    evidence_by_note: dict[str, list[str]] = {}
    for item in evidence:
        if item.location_status != "exact":
            continue
        evidence_by_note.setdefault(item.note_id, []).append(item.evidence_id)

    result: list[Claim] = []
    seen: set[str] = set()
    for note in notes:
        linked_ids = list(dict.fromkeys(evidence_by_note.get(note.note_id, [])))
        for point in note.key_points:
            text = point.strip()
            if not text:
                continue
            identity = claim_id(note.task_id, note.section_id, text)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(
                Claim(
                    claim_id=identity,
                    task_id=note.task_id,
                    section_id=note.section_id,
                    text=text,
                    kind="factual",
                    importance="supporting",
                    event_start=note.event_start_date,
                    event_end=note.event_end_date,
                    evidence_ids=linked_ids,
                )
            )
    return result


class ClaimExtractorAgent:
    """最多调用模型两次，之后确定性降级。"""

    def __init__(
        self, model: Any, *, timeout_seconds: float = 60.0
    ) -> None:
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def aextract(
        self,
        task: ResearchTask,
        notes: Sequence[ResearchNote],
        evidence: Sequence[Evidence],
        time_range: ResearchTimeRange | None,
    ) -> tuple[list[Claim], TokenUsage, bool]:
        total = TokenUsage()
        messages = build_claim_extractor_messages(
            task, notes, evidence, time_range
        )
        evidence_map = {item.evidence_id: item for item in evidence}
        validation_error = ""
        for attempt in range(2):
            attempt_messages = list(messages)
            if attempt and validation_error:
                attempt_messages.append(
                    HumanMessage(
                        content=(
                            "上次输出校验失败，请只返回修正后的 JSON。"
                            f"校验错误：{validation_error}"
                        )
                    )
                )
            try:
                response = await asyncio.wait_for(
                    self._model.ainvoke(attempt_messages),
                    timeout=self._timeout_seconds,
                )
                total = add_usage(total, message_usage(response))
                parsed = parse_claim_output(message_text(response))
                return (
                    materialize_claims(
                        parsed.claims, evidence_map, task, time_range
                    ),
                    total,
                    False,
                )
            except Exception as exc:
                validation_error = str(exc)
        return fallback_claims(notes, evidence), total, True
