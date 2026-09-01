"""阶段 3 的研究时间范围、任务与计划模型。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ResearchTimeRange(BaseModel):
    """用户明确给出的研究时间边界；无法解析时保留原始描述。"""

    start_date: date | None = None
    end_date: date | None = None
    description: str = ""


class ResearchTask(BaseModel):
    """Planner 生成并由 Researcher 串行执行的单个研究任务。"""

    task_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    planned_queries: list[str] = Field(min_length=1, max_length=3)
    expected_topics: list[str] = Field(min_length=1)
    min_sources: int = Field(default=2, ge=1, le=5)


class ResearchPlan(BaseModel):
    """规范化问题及其有界、互补的研究任务集合。"""

    plan_id: str = Field(min_length=1)
    original_query: str = Field(min_length=1)
    normalized_query: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    language: str = Field(min_length=1)
    time_range: ResearchTimeRange | None = None
    tasks: list[ResearchTask] = Field(min_length=1, max_length=5)
    report_outline: list[str] = Field(min_length=1)
