"""Planner、Researcher 与 Writer 共用的模型消息辅助函数。"""

from __future__ import annotations

import json
from typing import Any

from deeptrace.models import TokenUsage


def message_text(message: Any) -> str:
    """把 provider 消息内容稳定转换为文本。"""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    return json.dumps(content, ensure_ascii=False)


def message_usage(message: Any) -> TokenUsage:
    """从 LangChain 标准 usage_metadata 提取真实 provider 用量。"""
    metadata = getattr(message, "usage_metadata", None) or {}
    input_tokens = int(metadata.get("input_tokens", 0) or 0)
    output_tokens = int(metadata.get("output_tokens", 0) or 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=int(
            metadata.get("total_tokens", input_tokens + output_tokens)
            or input_tokens + output_tokens
        ),
    )


def add_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
    """累加两个模型调用的 TokenUsage，不修改输入。"""
    return TokenUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )
