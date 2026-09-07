"""基础研究模式的搜索查询规划。"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Mapping, Sequence

import json_repair

from deeptrace.models import TokenUsage, add_usage, message_text, message_usage
from deeptrace.prompts.planner import build_planner_messages

_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"


def normalize_question(question: str) -> str:
    """折叠异常空白，并修复被空格拆开的相邻中文字符。"""
    normalized = re.sub(r"\s+", " ", question).strip()
    return re.sub(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])", "", normalized)


def parse_search_queries(raw: str) -> list[str]:
    """从可修复 JSON 列表或对象中读取搜索查询。"""
    try:
        payload = json_repair.loads(raw.strip())
    except Exception as exc:
        raise ValueError("Planner JSON 无法解析") from exc

    if isinstance(payload, dict):
        payload = payload.get("queries")
    if not isinstance(payload, list):
        raise ValueError("Planner 必须返回查询列表")

    queries: list[str] = []
    for value in payload:
        if not isinstance(value, str):
            continue
        normalized = normalize_question(value)
        if normalized:
            queries.append(normalized)
    if not queries:
        raise ValueError("Planner 未返回有效查询")
    return queries


def _stable_unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


class PlannerAgent:
    """一次生成扁平搜索查询，失败时重试一次后降级。"""

    def __init__(
        self,
        model: Any,
        *,
        query_count: int = 3,
        call_timeout_seconds: float = 60.0,
    ) -> None:
        self._model = model
        self._query_count = max(0, query_count)
        self._call_timeout_seconds = call_timeout_seconds

    async def aplan(
        self,
        question: str,
        initial_results: Sequence[Mapping[str, Any]],
    ) -> tuple[list[str], TokenUsage, bool, str]:
        normalized_question = normalize_question(question)
        total = TokenUsage()
        messages = build_planner_messages(
            normalized_question,
            initial_results=initial_results,
            query_count=self._query_count,
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._call_timeout_seconds
        planner_error = ""

        for _attempt in range(2):
            remaining = deadline - loop.time()
            if remaining <= 0:
                planner_error = "Planner 调用超时"
                break
            try:
                response = await asyncio.wait_for(
                    self._model.ainvoke(messages), timeout=remaining
                )
                total = add_usage(total, message_usage(response))
                generated = parse_search_queries(message_text(response))[
                    : self._query_count
                ]
                return (
                    _stable_unique([*generated, normalized_question]),
                    total,
                    False,
                    "",
                )
            except TimeoutError:
                planner_error = "Planner 调用超时"
            except Exception as exc:
                planner_error = str(exc) or type(exc).__name__

        return [normalized_question], total, True, planner_error
