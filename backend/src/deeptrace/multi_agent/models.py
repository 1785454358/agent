"""Typed coordination state for the Supervisor Multi-Agent research mode."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
Summary = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)
]


class AssignmentDraft(BaseModel):
    """A task description proposed by the Supervisor before an ID is assigned."""

    model_config = ConfigDict(extra="forbid")

    objective: Text
    required_outputs: list[Text] = Field(min_length=1, max_length=3)
    excluded_scope: list[Text] = Field(default_factory=list, max_length=6)
    source_guidance: list[Text] = Field(default_factory=list, max_length=6)
    parent_ids: list[str] = Field(default_factory=list, max_length=6)


class ResearchAssignment(AssignmentDraft):
    """A stable, program-identified unit assigned to one Researcher."""

    id: str = Field(pattern=r"^r[1-9][0-9]{0,3}$")


class ResearcherResult(BaseModel):
    """Bounded task delivery used for coordination, not as Writer evidence."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^r[1-9][0-9]{0,3}$")
    status: Literal["completed", "partial", "blocked"]
    summary: Summary
    source_urls: list[str] = Field(default_factory=list, max_length=30)
    gaps: list[Text] = Field(default_factory=list, max_length=6)
    stop_reason: Literal[
        "completed",
        "round_limit",
        "local_tool_limit",
        "global_tool_limit",
        "provider_failure",
        "stagnant",
        "finalization_failed",
    ]

    @model_validator(mode="after")
    def validate_status(self) -> ResearcherResult:
        if self.status != "completed" and not self.gaps:
            raise ValueError("partial/blocked result requires specific gaps")
        if self.status == "completed" and self.gaps:
            raise ValueError("completed result cannot contain gaps")
        return self


class PlannedTask(BaseModel):
    """One persistent task record in the Multi-Agent research plan."""

    model_config = ConfigDict(extra="forbid")

    assignment: ResearchAssignment
    status: Literal["pending", "running", "completed", "partial", "blocked"] = (
        "pending"
    )
    result: ResearcherResult | None = None

    @model_validator(mode="after")
    def validate_result(self) -> PlannedTask:
        terminal = self.status in {"completed", "partial", "blocked"}
        if terminal != (self.result is not None):
            raise ValueError("terminal task status and result must agree")
        if self.result is not None and self.result.task_id != self.assignment.id:
            raise ValueError("task result ID must match assignment ID")
        return self


class SupervisorDecision(BaseModel):
    """One bounded Supervisor action after planning or reviewing a batch."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["dispatch", "finish"]
    rationale: Text
    assignments: list[AssignmentDraft] = Field(default_factory=list, max_length=6)
    sufficient: bool = False
    gaps: list[Text] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def validate_action(self) -> SupervisorDecision:
        if self.action == "dispatch" and not self.assignments:
            raise ValueError("dispatch requires assignments")
        if self.action == "finish" and self.assignments:
            raise ValueError("finish cannot contain assignments")
        if self.action == "dispatch" and self.sufficient:
            raise ValueError("dispatch cannot be sufficient")
        if self.action == "finish" and self.sufficient and self.gaps:
            raise ValueError("sufficient finish cannot contain material gaps")
        if self.action == "finish" and not self.sufficient and not self.gaps:
            raise ValueError("insufficient finish requires specific gaps")
        return self

    def validate_dispatch(
        self, *, executed_ids: set[str], max_batch_size: int
    ) -> None:
        if len(self.assignments) > max_batch_size:
            raise ValueError("dispatch exceeds max batch size")
        for assignment in self.assignments:
            if not set(assignment.parent_ids) <= executed_ids:
                raise ValueError("parent IDs must reference executed assignments")


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Text


class ResearchTopicArgs(SearchArgs):
    max_pages: int = Field(default=3, ge=1, le=5)


class FetchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    refresh: bool = False


def tool_schema(name: str, description: str, model: type[BaseModel]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": model.model_json_schema(),
        },
    }


SUPERVISOR_TOOL = tool_schema(
    "submit_supervisor_decision",
    "派发一批边界互斥的研究任务，或结束研究并说明整体充分性与缺口。",
    SupervisorDecision,
)

RESEARCH_TOOLS = [
    tool_schema(
        "research_topic",
        "围绕当前任务完成一次搜索并读取少量相关网页；适合建立资料基础。",
        ResearchTopicArgs,
    ),
    tool_schema("search_web", "搜索网页并返回摘要和 URL。", SearchArgs),
    tool_schema(
        "fetch_page", "读取搜索、用户输入或记忆中已知的 URL 原文。", FetchArgs
    ),
    tool_schema("search_memory", "检索有效期内的历史网页。", SearchArgs),
]

RESEARCHER_MODEL_TOOLS = [
    tool
    for tool in RESEARCH_TOOLS
    if tool["function"]["name"] != "search_web"
]

FINISH_TOOL = tool_schema(
    "finish_research",
    "交付当前研究任务的结果、实际读取来源、具体缺口与停止原因。",
    ResearcherResult,
)
