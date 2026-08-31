"""网页片段压缩为 ResearchNote 的集中提示词。"""

from __future__ import annotations

from typing import Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


COMPRESSION_SYSTEM_PROMPT = (
    "你是研究资料压缩器。只依据给定片段输出 JSON，字段为 "
    "title、key_points、evidence_snippets。证据摘录必须来自原文，"
    "不要输出 Markdown。"
)


def build_compression_messages(
    *,
    active_query: str,
    title: str,
    url: str,
    chunks: Sequence[tuple[int, str]],
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
            )
        ),
    ]
