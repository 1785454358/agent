"""阶段 3 的任务覆盖、章节结果与运行事件模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["pending", "running", "sufficient", "partial", "failed"]


class TaskCompletion(BaseModel):
    """Researcher 显式结束当前任务时提交的结构化结果。"""

    task_id: str
    summary: str
    covered_topics: list[str] = Field(default_factory=list)
    unresolved_topics: list[str] = Field(default_factory=list)


class TaskCoverage(BaseModel):
    """阶段 3 的基础流程覆盖状态，不代表 Claim 级验证。"""

    task_id: str
    status: TaskStatus = "pending"
    attempted_queries: list[str] = Field(default_factory=list)
    successful_source_urls: list[str] = Field(default_factory=list)
    relevant_note_ids: list[str] = Field(default_factory=list)
    covered_topics: list[str] = Field(default_factory=list)
    missing_topics: list[str] = Field(default_factory=list)
    rounds: int = Field(default=0, ge=0)
    consecutive_empty_rounds: int = Field(default=0, ge=0)
    failure_reason: str | None = None
    valid_note_ids: list[str] = Field(default_factory=list)
    retrospective_note_ids: list[str] = Field(default_factory=list)
    unknown_time_note_ids: list[str] = Field(default_factory=list)
    out_of_range_note_ids: list[str] = Field(default_factory=list)
    qualified_source_urls: list[str] = Field(default_factory=list)


class SectionResult(BaseModel):
    """单个研究任务交给 Writer 的有界章节输入。"""

    task_id: str
    section_id: str
    title: str
    summary: str
    note_ids: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    coverage: TaskCoverage
    errors: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    """可序列化的运行事件，CLI 当前显示 message。"""

    event_type: str
    message: str
    task_id: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )
