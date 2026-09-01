"""Planner 角色提示词。"""

from __future__ import annotations

from datetime import date

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


def build_planner_messages(
    question: str,
    *,
    today: date,
    max_tasks: int,
    queries_per_task: int,
) -> list[BaseMessage]:
    """构造只含用户问题和规划约束的 Planner 上下文。"""
    return [
        SystemMessage(
            content=(
                "你是 DeepTrace Planner。"
                f"当前日期为 {today.isoformat()}。"
                f"把问题拆成最多 {max_tasks} 个互补且不重复的研究任务，"
                f"每个任务生成 1 至 {queries_per_task} 条搜索查询。"
                "提取问题中的明确时间范围；相对时间必须依据当前日期解释，"
                "不能猜测用户没有表达的绝对日期。"
                "每个任务给出研究问题和预期主题，供基础覆盖判断。"
                "不得生成或猜测任何来源 URL。"
            )
        ),
        HumanMessage(content=question),
    ]
