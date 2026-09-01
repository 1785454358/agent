"""统一报告 Writer 的有界输入提示词。"""

from __future__ import annotations

import json
from typing import Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from deeptrace.models import ResearchNote, ResearchPlan, SectionResult


def build_writer_messages(
    *,
    plan: ResearchPlan,
    sections: Sequence[SectionResult],
    notes: Sequence[ResearchNote],
    termination_reason: str,
) -> list[BaseMessage]:
    """只把计划、章节结果和压缩笔记交给 Writer。"""
    plan_payload = {
        "objective": plan.objective,
        "language": plan.language,
        "time_range": (
            plan.time_range.model_dump(mode="json") if plan.time_range else None
        ),
        "report_outline": plan.report_outline,
    }
    section_payloads = [
        {
            "task_id": section.task_id,
            "section_id": section.section_id,
            "title": section.title,
            "summary": section.summary,
            "coverage": section.coverage.model_dump(mode="json"),
            "errors": section.errors,
            "note_ids": section.note_ids,
        }
        for section in sections
    ]
    note_payloads = [
        {
            "note_id": note.note_id,
            "title": note.title,
            "key_points": note.key_points,
            "evidence_snippets": note.evidence_snippets,
            "source_url": note.source_url,
            "source_published_at": note.source_published_at.isoformat() if note.source_published_at else None,
            "event_start_date": note.event_start_date.isoformat() if note.event_start_date else None,
            "event_end_date": note.event_end_date.isoformat() if note.event_end_date else None,
            "source_kind": note.source_kind,
            "temporal_relation": note.temporal_relation,
            "temporal_scope": note.temporal_scope,
        }
        for note in notes
    ]
    return [
        SystemMessage(
            content=(
                "你是 DeepTrace Writer，只依据输入的 ResearchNote 写报告。"
                "不得调用工具，不得补充笔记中不存在的事实。"
                "按计划生成执行摘要、分层正文、必要的对比表、局限说明和来源。"
                "必须使用 plan.language；明确研究时间范围。"
                "retrospective 信息必须写成后续回顾，不得把目标期外事件写成目标期进展。"
                "来源按一手或学术、后发回顾、其他来源分组。"
                "必须明确标记部分完成、执行失败和资料不足的章节。"
                "阶段 3 尚未实现 Claim 级验证，不得宣称事实已经过该级验证。"
                "used_note_ids 只列出报告实际使用且输入中存在的笔记 ID。"
                "只返回一个 JSON 对象，不要代码围栏或额外解释。"
                "JSON 必须包含 markdown 字符串和 used_note_ids 字符串数组。"
            )
        ),
        HumanMessage(
            content=json.dumps(
                {
                    "plan": plan_payload,
                    "sections": section_payloads,
                    "notes": note_payloads,
                    "termination_reason": termination_reason,
                },
                ensure_ascii=False,
            )
        ),
    ]
