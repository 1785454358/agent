"""Validated control state; source material remains ordinary page text."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class ResearchTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^t[1-9][0-9]{0,3}$")
    objective: Text
    success_criteria: Text
    depends_on: list[str] = Field(default_factory=list, max_length=6)


class ResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[ResearchTask] = Field(default_factory=list, max_length=6)
    finish: bool = False

    def validate_dependencies(self, completed: set[str]) -> None:
        ids = [task.id for task in self.tasks]
        if len(set(ids)) != len(ids) or set(ids) & completed:
            raise ValueError("任务 ID 重复或与已完成任务冲突")
        if self.finish and self.tasks:
            raise ValueError("结束研究时不能同时提交新任务")
        if not self.finish and not self.tasks:
            raise ValueError("计划不能为空")
        resolved = set(completed)
        pending = list(self.tasks)
        while pending:
            ready = [task for task in pending if set(task.depends_on) <= resolved]
            if not ready:
                raise ValueError("计划存在未知依赖或循环依赖")
            resolved.update(task.id for task in ready)
            pending = [task for task in pending if task not in ready]


class TaskFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # completed：清单全部满足；partial：有相关资料但清单未完成/未确认；
    # blocked：没有可用资料、无法继续。
    status: Literal["completed", "partial", "blocked"]
    gaps: list[Text] = Field(default_factory=list, max_length=6)


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Text


class ResearchTopicArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Text
    max_pages: int = Field(
        default=3, ge=1, le=5, description="本次最多抓取的候选页数"
    )


class ReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    refresh: bool = Field(
        default=False, description="为最新事实绕过历史页面缓存，重新联网抓取"
    )


def tool_schema(name: str, description: str, model: type[BaseModel]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": model.model_json_schema(),
        },
    }


PLAN_TOOL = tool_schema(
    "submit_plan", "提交待执行研究计划，或在资料充分时结束研究。", ResearchPlan
)
EXECUTOR_TOOLS = [
    tool_schema(
        "research_topic",
        "针对一个研究方向一次性完成搜索、去重、候选筛选与批量抓取，返回各来源的精简原文。"
        "优先用它建立资料基础；仅在需要补查特定页面时再单独用 fetch_page。",
        ResearchTopicArgs,
    ),
    tool_schema(
        "search_web",
        "搜索网页；返回摘要和 URL，重要结论需 fetch_page 阅读原文。",
        SearchArgs,
    ),
    tool_schema(
        "fetch_page",
        "阅读用户指定、搜索或记忆检索已返回的 URL，获得可引用原文。refresh=true 可核验最新页面。",
        ReadArgs,
    ),
    tool_schema(
        "search_memory",
        "按语义检索有效期内的历史页面；返回 URL 和时间，需 fetch_page 阅读。",
        SearchArgs,
    ),
    tool_schema(
        "finish_task",
        "结束当前子任务，报告完成/受阻和缺口。不能与其他工具同时调用。",
        TaskFeedback,
    ),
]
