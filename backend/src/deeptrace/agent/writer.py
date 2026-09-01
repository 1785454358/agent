"""统一报告 Writer 与确定性 Markdown 降级渲染。"""

from __future__ import annotations

from typing import Any, Sequence

import json_repair
from pydantic import BaseModel, Field

from deeptrace.agent._shared import add_usage, message_text, message_usage
from deeptrace.models import ResearchNote, ResearchPlan, SectionResult, TokenUsage
from deeptrace.prompts.writer import build_writer_messages


class WriterOutput(BaseModel):
    markdown: str = Field(min_length=1)
    used_note_ids: list[str] = Field(default_factory=list)


def parse_writer_output(raw: str) -> WriterOutput:
    """从普通 Provider 文本中提取、修复并严格校验 Writer JSON。"""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Writer 未返回 JSON 对象")
    try:
        payload = json_repair.loads(raw[start : end + 1])
        return WriterOutput.model_validate(payload)
    except Exception as exc:
        raise ValueError("Writer JSON 无法校验") from exc


def render_fallback_report(
    plan: ResearchPlan,
    sections: Sequence[SectionResult],
    notes: Sequence[ResearchNote],
    termination_reason: str,
) -> WriterOutput:
    """模型连续失败时保留所有已完成章节与结构化缺口。"""
    notes_by_id = {note.note_id: note for note in notes}
    used_note_ids: list[str] = []
    lines = [
        f"# {plan.objective}",
        "",
        "## 执行摘要",
        "",
        f"研究停止原因：`{termination_reason}`。以下内容仅基于抓取后研究笔记。",
    ]
    labels = {
        "sufficient": "完成",
        "partial": "部分完成",
        "failed": "执行失败",
        "running": "部分完成",
        "pending": "未执行",
    }
    for section in sections:
        label = labels[section.coverage.status]
        lines.extend(["", f"## {section.title}（{label}）", "", section.summary])
        if section.coverage.failure_reason:
            lines.append(f"失败或缺口原因：`{section.coverage.failure_reason}`。")
        if section.coverage.missing_topics:
            lines.append("未覆盖主题：" + "、".join(section.coverage.missing_topics))
        if section.errors:
            lines.append("执行错误：" + "；".join(section.errors))
        for note_id in section.note_ids:
            note = notes_by_id.get(note_id)
            if note is None:
                continue
            if note_id not in used_note_ids:
                used_note_ids.append(note_id)
            for point in note.key_points:
                lines.append(f"- {point}")
    lines.extend(
        [
            "",
            "## 局限说明",
            "",
            "本报告基于抓取后研究笔记生成；阶段 3 尚未实现 Claim 级证据验证。",
        ]
    )
    used_notes = [notes_by_id[item] for item in used_note_ids]
    if used_notes:
        lines.extend(["", "## 来源", ""])
        seen_urls: set[str] = set()
        for note in used_notes:
            if note.source_url in seen_urls:
                continue
            seen_urls.add(note.source_url)
            lines.append(f"- [{note.title}]({note.source_url})")
    return WriterOutput(markdown="\n".join(lines), used_note_ids=used_note_ids)


class WriterAgent:
    """结构化生成最终报告，失败时重试一次再确定性降级。"""

    def __init__(self, model: Any) -> None:
        self._model = model

    async def awrite(
        self,
        *,
        plan: ResearchPlan,
        sections: Sequence[SectionResult],
        notes: Sequence[ResearchNote],
        termination_reason: str,
    ) -> tuple[WriterOutput, TokenUsage, bool]:
        messages = build_writer_messages(
            plan=plan,
            sections=sections,
            notes=notes,
            termination_reason=termination_reason,
        )
        total = TokenUsage()
        allowed_ids = {note.note_id for note in notes}
        for _attempt in range(2):
            try:
                response = await self._model.ainvoke(messages)
                total = add_usage(total, message_usage(response))
                parsed = parse_writer_output(message_text(response))
                clean = parsed.model_copy(
                    update={
                        "used_note_ids": [
                            item
                            for item in parsed.used_note_ids
                            if item in allowed_ids
                        ]
                    }
                )
                return clean, total, False
            except Exception:
                continue
        return (
            render_fallback_report(plan, sections, notes, termination_reason),
            total,
            True,
        )
