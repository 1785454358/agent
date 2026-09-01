"""网页片段压缩为 ResearchNote 的集中提示词。"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from deeptrace.models import ResearchTimeRange


COMPRESSION_SYSTEM_PROMPT = (
    "你是研究资料压缩器。只依据给定片段输出 JSON，字段为 "
    "title、key_points、evidence_snippets、event_start_date、event_end_date、"
    "source_kind、temporal_scope。证据摘录必须来自原文，"
    "有时间范围时只保留范围内事件；后发文章可以回顾范围内事件。"
    "事件日期必须由给定片段中的明确日期或年份直接支持；无法直接支持时返回 null，"
    "不得根据问题中的目标年份、页面标题或常识推断事件日期。"
    "目标范围之后才发布的模型、产品、实验或系统属于范围外事件，不能写成目标期进展。"
    "source_kind 只能是 official、academic、reputable_secondary、other、unknown。"
    "不要输出 Markdown。"
)


def build_compression_messages(
    *,
    active_query: str,
    title: str,
    url: str,
    chunks: Sequence[tuple[int, str]],
    time_range: ResearchTimeRange | None = None,
    source_published_at: datetime | None = None,
    publisher: str | None = None,
) -> list[BaseMessage]:
    """根据纯文本参数构造压缩消息，不读取运行状态。"""
    excerpts = "\n\n".join(
        f"[片段 {index}]\n{text}" for index, text in chunks
    )
    return [
        SystemMessage(content=COMPRESSION_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"当前子问题：{active_query}\n"
                f"页面标题：{title}\n"
                f"页面 URL：{url}\n\n{excerpts}"
                f"\n研究时间范围：{json.dumps(time_range.model_dump(mode='json') if time_range else None, ensure_ascii=False)}"
                f"\n来源发布时间：{source_published_at.isoformat() if source_published_at else 'unknown'}"
                f"\n发布机构：{publisher or 'unknown'}"
            )
        ),
    ]
