"""结构化研究 Planner、问题规范化与确定性降级。"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from deeptrace.agent._shared import add_usage, message_usage
from deeptrace.models import (
    ResearchPlan,
    ResearchTask,
    ResearchTimeRange,
    TokenUsage,
)
from deeptrace.prompts.planner import build_planner_messages

_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"


class PlannerTaskDraft(BaseModel):
    """模型负责语义内容，稳定 ID 由服务生成。"""

    title: str
    question: str
    planned_queries: list[str] = Field(min_length=1, max_length=3)
    expected_topics: list[str] = Field(min_length=1)


class PlannerDraft(BaseModel):
    """Planner 模型的结构化输出边界。"""

    objective: str
    language: str = "zh-CN"
    time_range: ResearchTimeRange | None = None
    tasks: list[PlannerTaskDraft] = Field(min_length=2, max_length=5)
    report_outline: list[str] = Field(min_length=1)


def normalize_question(question: str) -> str:
    """折叠异常空白，并修复被空格拆开的相邻中文字符。"""
    normalized = re.sub(r"\s+", " ", question).strip()
    return re.sub(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])", "", normalized)


def _unique_nonempty(values: list[str]) -> list[str]:
    normalized = [normalize_question(value) for value in values]
    return list(dict.fromkeys(value for value in normalized if value))


def _plan_id(normalized_query: str, tasks: list[ResearchTask]) -> str:
    payload = json.dumps(
        {
            "query": normalized_query,
            "tasks": [task.model_dump(mode="json") for task in tasks],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"plan-{digest}"


def materialize_plan(
    question: str,
    draft: PlannerDraft,
    max_tasks: int,
    min_sources: int,
) -> ResearchPlan:
    """校正模型草稿，并生成稳定的任务、章节与计划 ID。"""
    normalized_query = normalize_question(question)
    tasks: list[ResearchTask] = []
    for index, item in enumerate(draft.tasks[:max_tasks], start=1):
        queries = _unique_nonempty(item.planned_queries)
        tasks.append(
            ResearchTask(
                task_id=f"task-{index:02d}",
                section_id=f"section-{index:02d}",
                title=normalize_question(item.title),
                question=normalize_question(item.question),
                planned_queries=queries,
                expected_topics=_unique_nonempty(item.expected_topics),
                min_sources=min_sources,
            )
        )
    outline = _unique_nonempty(draft.report_outline)[: len(tasks)]
    if not outline:
        outline = [task.title for task in tasks]
    return ResearchPlan(
        plan_id=_plan_id(normalized_query, tasks),
        original_query=question,
        normalized_query=normalized_query,
        objective=normalize_question(draft.objective),
        language=draft.language.strip() or "zh-CN",
        time_range=draft.time_range,
        tasks=tasks,
        report_outline=outline,
    )


def build_fallback_plan(question: str, min_sources: int) -> ResearchPlan:
    """结构化规划连续失败时保留原问题的单任务降级计划。"""
    normalized_query = normalize_question(question)
    task = ResearchTask(
        task_id="task-01",
        section_id="section-01",
        title="研究结果",
        question=normalized_query,
        planned_queries=[normalized_query],
        expected_topics=["问题全貌"],
        min_sources=min_sources,
    )
    return ResearchPlan(
        plan_id=_plan_id(normalized_query, [task]),
        original_query=question,
        normalized_query=normalized_query,
        objective=normalized_query,
        language="zh-CN",
        tasks=[task],
        report_outline=[task.title],
    )


class PlannerAgent:
    """调用结构化模型生成计划，失败时重试一次再确定性降级。"""

    def __init__(
        self,
        model: Any,
        *,
        max_tasks: int,
        queries_per_task: int,
        min_sources: int,
    ) -> None:
        self._structured_model = model.with_structured_output(
            PlannerDraft, include_raw=True
        )
        self._max_tasks = max_tasks
        self._queries_per_task = queries_per_task
        self._min_sources = min_sources

    async def aplan(self, question: str) -> tuple[ResearchPlan, TokenUsage, bool]:
        total = TokenUsage()
        messages = build_planner_messages(
            question,
            today=date.today(),
            max_tasks=self._max_tasks,
            queries_per_task=self._queries_per_task,
        )
        for _attempt in range(2):
            try:
                result = await self._structured_model.ainvoke(messages)
                total = add_usage(total, message_usage(result.get("raw")))
                parsed = result.get("parsed")
                if isinstance(parsed, PlannerDraft):
                    return (
                        materialize_plan(
                            question,
                            parsed,
                            self._max_tasks,
                            self._min_sources,
                        ),
                        total,
                        False,
                    )
            except Exception:
                continue
        return build_fallback_plan(question, self._min_sources), total, True
