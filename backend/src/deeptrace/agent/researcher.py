"""任务级 Researcher 决策与显式完成协议。"""

from __future__ import annotations

from typing import Any, Literal, Sequence

from langchain_core.messages import AIMessage, BaseMessage

from deeptrace.agent._shared import message_text, message_usage
from deeptrace.models import (
    ResearchNote,
    ResearchTask,
    TaskCompletion,
    TaskCoverage,
    TokenUsage,
)
from deeptrace.prompts.researcher import build_researcher_messages
from deeptrace.tools import RESEARCHER_TOOL_SCHEMAS


def parse_task_completion(
    tool_call: dict[str, Any], expected_task_id: str
) -> TaskCompletion:
    """解析完成工具，并拒绝结束非当前任务。"""
    if tool_call.get("name") != "complete_research_task":
        raise ValueError("tool_call 不是 complete_research_task")
    completion = TaskCompletion.model_validate(tool_call.get("args", {}))
    if completion.task_id != expected_task_id:
        raise ValueError(
            f"task_id 不匹配：期望 {expected_task_id}，实际 {completion.task_id}"
        )
    return completion


class ResearcherAgent:
    """将模型约束在当前任务和阶段 3 工具集合内。"""

    def __init__(self, model: Any) -> None:
        self._model = model.bind_tools(RESEARCHER_TOOL_SCHEMAS)

    async def adecide(
        self,
        *,
        user_query: str,
        task: ResearchTask,
        coverage: TaskCoverage,
        notes: Sequence[ResearchNote],
        recent_messages: Sequence[BaseMessage],
        budget_summary: str,
        existing_source_identities: Sequence[str] = (),
    ) -> tuple[AIMessage, TokenUsage]:
        messages = build_researcher_messages(
            user_query=user_query,
            task=task,
            coverage=coverage,
            notes=notes,
            recent_messages=recent_messages,
            budget_summary=budget_summary,
            existing_source_identities=existing_source_identities,
        )
        response = await self._model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            response = AIMessage(content=message_text(response))
        return response, message_usage(response)
