"""片段直写 Writer 的提示词：材料来自压缩笔记原文，引用由系统机械拼接。"""

from __future__ import annotations

import json
from typing import Any, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from deeptrace.models import ResearchPlan


WRITER_SYSTEM_PROMPT = (
    "你是 DeepTrace Report Writer。只能依据输入材料写作：每个小节提供研究"
    "笔记的要点与逐字摘录，摘录来自编号来源。正文用 Markdown 写作，第一行是"
    "“# 标题”，每个小节用“## 小节标题”。引用来源时在句子末尾标注 [^编号]，"
    "编号只能来自输入的 sources 列表；不得编造编号或 URL，不得自己输出脚注"
    "定义或“## 来源”章节（系统会统一拼接）。材料不足以确认的内容使用"
    "“现有证据显示”“材料尚不足”等措辞；完全缺失的小节写成“局限”。"
    "不得补充外部知识。只返回 Markdown 正文，不要 JSON，不要用代码块包裹。"
)


def build_writer_messages(
    *,
    plan: ResearchPlan,
    sources: Sequence[dict[str, Any]],
    sections: Sequence[dict[str, Any]],
    termination_reason: str,
    correction: str | None = None,
) -> list[BaseMessage]:
    """发送编号来源与逐字材料，不发送 RawDocument 正文，也不发送 Claim JSON。"""
    payload = {
        "plan": {
            "objective": plan.objective,
            "language": plan.language,
            "time_range": (
                plan.time_range.model_dump(mode="json")
                if plan.time_range
                else None
            ),
            "report_outline": plan.report_outline,
        },
        "sources": list(sources),
        "sections": list(sections),
        "termination_reason": termination_reason,
    }
    messages = [
        SystemMessage(content=WRITER_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]
    if correction:
        messages.append(HumanMessage(content=correction))
    return messages
