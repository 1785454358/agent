"""Planner 角色提示词。"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


def build_planner_messages(
    question: str,
    *,
    initial_results: Sequence[Mapping[str, Any]],
    query_count: int,
) -> list[BaseMessage]:
    """构造一条系统指令和一条 JSON 用户输入。"""
    payload = {
        "question": question,
        "initial_results": list(initial_results),
        "query_count": query_count,
    }
    return [
        SystemMessage(
            content=(
                "你是 DeepTrace 搜索查询规划器。"
                "根据用户问题和初始搜索结果，生成互补、不重复的搜索查询。"
                "查询应直接可用于搜索引擎，不得生成或猜测 URL。"
                "只返回 JSON 字符串列表，或包含 queries 字段的 JSON 对象；"
                "不要 Markdown、解释或代码围栏。"
            )
        ),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
    ]
