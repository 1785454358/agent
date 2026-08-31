# 阶段 3 规划式 Deep Research 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在阶段 2 的真实搜索、可靠抓取和上下文压缩能力上，实现 Planner、Researcher、Writer 驱动的规划式 Deep Research。

**Architecture:** 使用一个 LangGraph 管理“规划 → 逐任务研究 → 工具循环 → 任务收尾 → 统一写作”。角色模型调用放在 `agent/`，搜索抓取与压缩执行放在独立工具执行器，LangGraph 节点只负责状态协调；阶段 3 串行执行研究任务，同一轮网页抓取和压缩保持有界并发。

**Tech Stack:** Python 3.11+、Pydantic 2、LangChain、LangGraph、ChatOpenAI-compatible API、Tavily、BGE-M3、HTTPX、Trafilatura、BeautifulSoup、Playwright、pytest、uv

**Spec:** `docs/superpowers/specs/2026-09-01-stage-03-planned-deep-research-design.md`

## Global Constraints

- 代码直接修改正式 `backend/`，不创建隔离参考实现。
- 保留阶段 2 的搜索、抓取降级链、BGE-M3 双查询召回、压缩降级和 Token 统计。
- State 只保存可序列化数据；numpy 向量只保存在 `CompressionRuntime`。
- 网页全文不能进入 Planner、Researcher 主上下文或 Writer 上下文。
- 阶段 3 不实现 Evidence Store、Verifier、Memory、数据库、API、Web UI、MCP 或规模化评测。
- 自动化测试只覆盖纯模型、路由和确定性逻辑，不用 Fake 搜索结果或 Fake 模型答案冒充验收。
- 最终验收必须使用真实 LLM、Tavily 和网页抓取。
- 费用只在明确配置模型单价时计算；价格未知时显示 `unavailable`。
- 保留必要中文注释；提示词统一放在 `prompts/`。
- 工作区可能包含用户未提交的删除和修改，只提交当前任务列出的文件，禁止恢复或覆盖无关改动。

---

### Task 1: 阶段 3 数据模型与 reducer

**Files:**
- Create: `backend/src/deeptrace/models/plan.py`
- Create: `backend/src/deeptrace/models/report.py`
- Modify: `backend/src/deeptrace/models/research.py`
- Modify: `backend/src/deeptrace/models/__init__.py`
- Modify: `backend/src/deeptrace/orchestration/state.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/models/test_plan.py`
- Test: `backend/tests/orchestration/test_state.py`

**Interfaces:**
- Produces: `ResearchTimeRange`, `ResearchTask`, `ResearchPlan`, `TaskCompletion`
- Produces: `TaskCoverage`, `SectionResult`, `RunEvent`
- Produces: `merge_token_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage`
- Changes: `ResearchNote.task_id: str` and `ResearchNote.section_id: str`
- Later tasks consume these exact public model names from `deeptrace.models`.

- [ ] **Step 1: Write model validation tests**

```python
# tests/models/test_plan.py
from datetime import date

import pytest
from pydantic import ValidationError

from deeptrace.models import (
    ResearchPlan,
    ResearchTask,
    ResearchTimeRange,
    RunEvent,
    TaskCoverage,
)


def test_research_plan_accepts_bounded_serializable_tasks() -> None:
    task = ResearchTask(
        task_id="task-01",
        section_id="section-01",
        title="技术进展",
        question="2024 年有哪些关键技术进展？",
        planned_queries=["2024 AI Agent 技术进展"],
        expected_topics=["规划", "工具调用"],
        min_sources=2,
    )
    plan = ResearchPlan(
        plan_id="plan-abc",
        original_query="2024年 AI Agent 进展",
        normalized_query="2024年 AI Agent 进展",
        objective="总结年度进展",
        language="zh-CN",
        time_range=ResearchTimeRange(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            description="2024 年",
        ),
        tasks=[task, task.model_copy(update={
            "task_id": "task-02",
            "section_id": "section-02",
            "title": "应用进展",
        })],
        report_outline=["技术进展", "应用进展"],
    )

    assert plan.model_dump(mode="json")["time_range"]["start_date"] == "2024-01-01"


def test_research_plan_rejects_more_than_five_tasks() -> None:
    task = ResearchTask(
        task_id="task-01", section_id="section-01", title="主题",
        question="问题", planned_queries=["查询"],
        expected_topics=["主题"], min_sources=2,
    )
    with pytest.raises(ValidationError):
        ResearchPlan(
            plan_id="plan", original_query="问题", normalized_query="问题",
            objective="目标", language="zh-CN", tasks=[task] * 6,
            report_outline=["主题"],
        )


def test_run_event_details_are_not_shared() -> None:
    first = RunEvent(event_type="planning.started", message="开始")
    second = RunEvent(event_type="planning.started", message="开始")
    first.details["count"] = 1
    assert second.details == {}
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
cd backend
uv run pytest tests/models/test_plan.py -v
```

Expected: collection fails because the stage 3 models do not exist.

- [ ] **Step 3: Implement the public models**

Use bounded fields so invalid model output is rejected at the boundary:

```python
# models/plan.py
from datetime import date
from pydantic import BaseModel, Field


class ResearchTimeRange(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    description: str = ""


class ResearchTask(BaseModel):
    task_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    planned_queries: list[str] = Field(min_length=1, max_length=3)
    expected_topics: list[str] = Field(min_length=1)
    min_sources: int = Field(default=2, ge=1, le=5)


class ResearchPlan(BaseModel):
    plan_id: str = Field(min_length=1)
    original_query: str = Field(min_length=1)
    normalized_query: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    language: str = Field(min_length=1)
    time_range: ResearchTimeRange | None = None
    tasks: list[ResearchTask] = Field(min_length=1, max_length=5)
    report_outline: list[str] = Field(min_length=1)
```

```python
# models/report.py
from typing import Literal
from pydantic import BaseModel, Field

TaskStatus = Literal["pending", "running", "sufficient", "partial", "failed"]


class TaskCompletion(BaseModel):
    task_id: str
    summary: str
    covered_topics: list[str] = Field(default_factory=list)
    unresolved_topics: list[str] = Field(default_factory=list)


class TaskCoverage(BaseModel):
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


class SectionResult(BaseModel):
    task_id: str
    section_id: str
    title: str
    summary: str
    note_ids: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    coverage: TaskCoverage
    errors: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    event_type: str
    message: str
    task_id: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
```

Add `task_id` and `section_id` to every `ResearchNote` construction site in later tasks; do not temporarily make them optional.

- [ ] **Step 4: Add exact shared model fixtures**

```python
# tests/conftest.py
from datetime import UTC, datetime
import pytest

from deeptrace.models import (
    RawDocument, ResearchNote, ResearchPlan, ResearchTask, ScraperUsed,
    SectionResult, TaskCompletion, TaskCoverage,
)


@pytest.fixture
def research_task() -> ResearchTask:
    return ResearchTask(
        task_id="task-01", section_id="section-01", title="技术进展",
        question="有哪些技术进展？", planned_queries=["AI Agent 技术进展"],
        expected_topics=["规划", "工具调用"], min_sources=2,
    )


@pytest.fixture
def task_coverage(research_task) -> TaskCoverage:
    return TaskCoverage(task_id=research_task.task_id)


@pytest.fixture
def running_coverage(research_task) -> TaskCoverage:
    return TaskCoverage(task_id=research_task.task_id, status="running")


@pytest.fixture
def task_completion(research_task) -> TaskCompletion:
    return TaskCompletion(
        task_id=research_task.task_id, summary="完成技术研究",
        covered_topics=["规划", "工具调用"], unresolved_topics=[],
    )


@pytest.fixture
def research_note(research_task) -> ResearchNote:
    return ResearchNote(
        note_id="note-01", doc_id="doc-01", task_id=research_task.task_id,
        section_id=research_task.section_id, active_query="AI Agent 技术进展",
        title="来源标题", key_points=["关键进展"], evidence_snippets=["原文摘录"],
        source_url="https://example.com/a", relevance_score=0.8,
        compression_status="compressed",
    )


@pytest.fixture
def research_plan(research_task) -> ResearchPlan:
    second = research_task.model_copy(update={
        "task_id": "task-02", "section_id": "section-02", "title": "应用进展",
    })
    return ResearchPlan(
        plan_id="plan-01", original_query="年度进展", normalized_query="年度进展",
        objective="总结年度进展", language="zh-CN",
        tasks=[research_task, second], report_outline=["技术进展", "应用进展"],
    )


@pytest.fixture
def section_result(research_task, research_note) -> SectionResult:
    coverage = TaskCoverage(
        task_id=research_task.task_id, status="sufficient",
        successful_source_urls=[research_note.source_url],
        relevant_note_ids=[research_note.note_id],
    )
    return SectionResult(
        task_id=research_task.task_id, section_id=research_task.section_id,
        title=research_task.title, summary="完成技术研究",
        note_ids=[research_note.note_id], source_urls=[research_note.source_url],
        coverage=coverage,
    )


@pytest.fixture
def partial_section(section_result) -> SectionResult:
    return section_result.model_copy(update={
        "coverage": section_result.coverage.model_copy(update={
            "status": "partial", "failure_reason": "token_budget",
        })
    })


@pytest.fixture
def raw_document() -> RawDocument:
    return RawDocument(
        doc_id="doc-01", requested_url="https://example.com/a",
        final_url="https://example.com/a", canonical_url="https://example.com/a",
        title="来源标题", content="整页正文唯一标记", content_hash="hash",
        fetched_at=datetime.now(UTC), scraper_used=ScraperUsed.HTTPX_TRAFILATURA,
        status="success",
    )
```

- [ ] **Step 5: Extend GraphState and test reducers**

Add these fields:

```python
research_plan: ResearchPlan | None
current_task_index: int
task_coverages: Annotated[dict[str, TaskCoverage], merge_dicts]
section_results: Annotated[dict[str, SectionResult], merge_dicts]
pending_task_completion: TaskCompletion | None
force_finalize: bool
events: Annotated[list[RunEvent], operator.add]
started_at: str
fetched_page_count: Annotated[int, operator.add]
api_token_count: Annotated[int, operator.add]
estimated_cost_usd: Annotated[float, operator.add]
used_note_ids: list[str]
```

Replace the old `events: list[str]` contract instead of keeping two event fields. Add reducer assertions to `tests/orchestration/test_state.py`.

- [ ] **Step 6: Run focused and existing state tests**

Run:

```powershell
uv run pytest tests/models/test_plan.py tests/orchestration/test_state.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```powershell
git add backend/src/deeptrace/models backend/src/deeptrace/orchestration/state.py backend/tests/conftest.py backend/tests/models/test_plan.py backend/tests/orchestration/test_state.py
git commit -m "feat: add planned research state models"
```

---

### Task 2: Planner 与查询规范化

**Files:**
- Create: `backend/src/deeptrace/prompts/planner.py`
- Create: `backend/src/deeptrace/agent/planner.py`
- Create: `backend/src/deeptrace/agent/_shared.py`
- Test: `backend/tests/agent/test_planner.py`

**Interfaces:**
- Produces: `normalize_question(question: str) -> str`
- Produces: `materialize_plan(question: str, draft: PlannerDraft, max_tasks: int, min_sources: int) -> ResearchPlan`
- Produces: `build_fallback_plan(question: str, min_sources: int) -> ResearchPlan`
- Produces: `PlannerAgent.aplan(question: str) -> tuple[ResearchPlan, TokenUsage, bool]`; final bool is `used_fallback`.
- Produces: `message_text(message: Any) -> str`, `message_usage(message: Any) -> TokenUsage` and `add_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage` in `agent/_shared.py`.
- Consumes: unbound LLM model and current date supplied to the prompt builder.

- [ ] **Step 1: Write deterministic Planner tests**

```python
from deeptrace.agent.planner import (
    build_fallback_plan,
    normalize_question,
)


def test_normalize_question_collapses_whitespace() -> None:
    assert normalize_question("  2024年AI Agent领域有哪 些进展？  ") == (
        "2024年AI Agent领域有哪些进展？"
    )


def test_fallback_plan_is_single_task_and_preserves_question() -> None:
    plan = build_fallback_plan("2024 年 Agent 进展", min_sources=2)
    assert len(plan.tasks) == 1
    assert plan.tasks[0].question == plan.normalized_query
    assert plan.tasks[0].min_sources == 2
```

Normalization must repair whitespace splitting Chinese characters while retaining necessary spaces between Latin words; implement this with explicit regexes and tests, not a blanket removal of all spaces.

- [ ] **Step 2: Run Planner tests and confirm failure**

Run: `uv run pytest tests/agent/test_planner.py -v`

Expected: import failure for `deeptrace.agent.planner`.

- [ ] **Step 3: Implement prompt and draft boundary**

`prompts/planner.py` exports:

```python
def build_planner_messages(
    question: str,
    *,
    today: date,
    max_tasks: int,
    queries_per_task: int,
) -> list[BaseMessage]:
    return [
        SystemMessage(content=(
            "你是 DeepTrace Planner。"
            f"当前日期为 {today.isoformat()}。"
            f"把问题拆成最多 {max_tasks} 个互补研究任务，"
            f"每个任务最多 {queries_per_task} 条查询。"
            "提取明确时间范围；不得生成或猜测来源 URL。"
            "每个任务给出预期主题，供基础覆盖判断。"
        )),
        HumanMessage(content=question),
    ]
```

The prompt must require complementary tasks, explicit time scope, 1–3 queries per task, expected topics, and no invented source URLs.

Keep model-owned draft types private to `agent/planner.py`:

```python
class PlannerTaskDraft(BaseModel):
    title: str
    question: str
    planned_queries: list[str] = Field(min_length=1, max_length=3)
    expected_topics: list[str] = Field(min_length=1)


class PlannerDraft(BaseModel):
    objective: str
    language: str = "zh-CN"
    time_range: ResearchTimeRange | None = None
    tasks: list[PlannerTaskDraft] = Field(min_length=2, max_length=5)
    report_outline: list[str] = Field(min_length=1)
```

`materialize_plan` assigns `task-01`, `section-01` and a plan hash; it trims the draft to configured limits and deduplicates exact queries.

- [ ] **Step 4: Implement PlannerAgent with one retry and fallback**

```python
class PlannerAgent:
    def __init__(self, model: Any, *, max_tasks: int, queries_per_task: int,
                 min_sources: int) -> None:
        self._structured_model = model.with_structured_output(
            PlannerDraft, include_raw=True
        )
        self._max_tasks = max_tasks
        self._queries_per_task = queries_per_task
        self._min_sources = min_sources

    async def aplan(self, question: str) -> tuple[ResearchPlan, TokenUsage, bool]:
        total = TokenUsage()
        messages = build_planner_messages(
            question, today=date.today(), max_tasks=self._max_tasks,
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
                            question, parsed, self._max_tasks, self._min_sources
                        ),
                        total,
                        False,
                    )
            except Exception:
                continue
        return build_fallback_plan(question, self._min_sources), total, True
```

`agent/_shared.py` extracts usage from `usage_metadata` exactly as the current `orchestration/nodes.py::_usage` does. The implementation catches `Exception` only, so `KeyboardInterrupt` and `SystemExit` are not swallowed.

- [ ] **Step 5: Run Planner tests**

Run: `uv run pytest tests/agent/test_planner.py -v`

Expected: PASS. No external API call occurs in these deterministic tests.

- [ ] **Step 6: Commit Task 2**

```powershell
git add backend/src/deeptrace/agent/_shared.py backend/src/deeptrace/agent/planner.py backend/src/deeptrace/prompts/planner.py backend/tests/agent/test_planner.py
git commit -m "feat: add structured research planner"
```

---

### Task 3: Researcher 角色与显式任务完成协议

**Files:**
- Create: `backend/src/deeptrace/prompts/researcher.py`
- Create: `backend/src/deeptrace/agent/researcher.py`
- Modify: `backend/src/deeptrace/tools/__init__.py`
- Test: `backend/tests/agent/test_researcher.py`

**Interfaces:**
- Produces: `EXTERNAL_TOOL_SCHEMAS` containing only `search_web` and `fetch_webpage`
- Produces: `COMPLETE_TASK_TOOL_SCHEMA` named `complete_research_task`
- Produces: `parse_task_completion(tool_call: dict[str, Any], expected_task_id: str) -> TaskCompletion`
- Produces: `ResearcherAgent.adecide` with the exact signature below, returning `tuple[AIMessage, TokenUsage]`.
- Consumes: current task, coverage, related notes, recent complete tool turns and budget summary.

- [ ] **Step 1: Write task completion and prompt-scope tests**

```python
import pytest

from deeptrace.agent.researcher import parse_task_completion
from deeptrace.prompts.researcher import build_researcher_messages


def test_parse_task_completion_rejects_wrong_task() -> None:
    call = {
        "name": "complete_research_task",
        "args": {
            "task_id": "task-02",
            "summary": "已完成",
            "covered_topics": ["工具调用"],
            "unresolved_topics": [],
        },
    }
    with pytest.raises(ValueError, match="task_id"):
        parse_task_completion(call, expected_task_id="task-01")


def test_researcher_prompt_contains_current_task_but_not_raw_document(
    research_task, task_coverage, research_note
) -> None:
    messages = build_researcher_messages(
        user_query="年度进展",
        task=research_task,
        coverage=task_coverage,
        notes=[research_note],
        recent_messages=[],
        budget_summary="剩余 2 轮",
    )
    serialized = "\n".join(str(message.content) for message in messages)
    assert research_task.question in serialized
    assert research_note.key_points[0] in serialized
    assert "整页正文唯一标记" not in serialized
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run pytest tests/agent/test_researcher.py -v`

- [ ] **Step 3: Split tool schemas and add completion schema**

```python
EXTERNAL_TOOL_SCHEMAS = [SEARCH_TOOL_SCHEMA, FETCH_TOOL_SCHEMA]

COMPLETE_TASK_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "complete_research_task",
        "description": "结束当前研究任务并报告覆盖与缺口，不执行外部操作。",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1},
                "summary": {"type": "string", "minLength": 1},
                "covered_topics": {"type": "array", "items": {"type": "string"}},
                "unresolved_topics": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "task_id", "summary", "covered_topics", "unresolved_topics"
            ],
            "additionalProperties": False,
        },
    },
}

RESEARCHER_TOOL_SCHEMAS = [
    *EXTERNAL_TOOL_SCHEMAS,
    COMPLETE_TASK_TOOL_SCHEMA,
]
```

Remove the ambiguous old `TOOL_SCHEMAS` export and update consumers in Task 7.

- [ ] **Step 4: Implement Researcher prompt and service**

`ResearcherAgent.adecide` signature:

```python
class ResearcherAgent:
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
    ) -> tuple[AIMessage, TokenUsage]:
        messages = build_researcher_messages(
            user_query=user_query, task=task, coverage=coverage, notes=notes,
            recent_messages=recent_messages, budget_summary=budget_summary,
        )
        response = await self._model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            response = AIMessage(content=message_text(response))
        return response, message_usage(response)
```

The prompt must require untried planned queries first, allow multiple tool calls in one response, prohibit final-report writing, and require `complete_research_task` when the task is done. Bind `RESEARCHER_TOOL_SCHEMAS` once in the constructor.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest tests/agent/test_researcher.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```powershell
git add backend/src/deeptrace/agent/researcher.py backend/src/deeptrace/prompts/researcher.py backend/src/deeptrace/tools/__init__.py backend/tests/agent/test_researcher.py
git commit -m "feat: add task-scoped researcher role"
```

---

### Task 4: 抽出研究工具执行器并标记任务归属

**Files:**
- Create: `backend/src/deeptrace/orchestration/tool_executor.py`
- Modify: `backend/src/deeptrace/context/compression.py`
- Modify: `backend/src/deeptrace/models/document.py`
- Modify: `backend/src/deeptrace/orchestration/nodes.py`
- Test: `backend/tests/orchestration/test_tool_executor.py`
- Modify Test: `backend/tests/context/test_compression.py`

**Interfaces:**
- Changes: `PendingFetch` and `CompressionRequest` include `task_id` and `section_id`
- Produces: `ToolExecutionUpdate` with messages, document/chunk/note updates, attempted queries, new-note count, fetched-page delta and errors
- Produces: `ResearchToolExecutor.aexecute(state: GraphState, tool_calls: Sequence[dict[str, Any]]) -> ToolExecutionUpdate`
- Preserves: `build_tool_messages`, `keep_recent_tool_turns` and `tool_call_id` order guarantees.

- [ ] **Step 1: Write task-attribution and ordering tests**

```python
def test_extractive_note_preserves_task_identity(raw_document) -> None:
    selection = ChunkSelection(
        chunks=[], is_relevant=False, top1_user_score=0.1,
        top1_active_score=0.2, top1_fused_score=0.2,
    )
    note = build_extractive_note(
        raw_document, selection, "当前查询", "task-01", "section-01", "失败",
    )
    assert note.task_id == "task-01"
    assert note.section_id == "section-01"


def test_external_results_keep_original_tool_order() -> None:
    calls = [
        {"id": "a", "name": "fetch_webpage", "args": {"url": "https://a"}},
        {"id": "b", "name": "fetch_webpage", "args": {"url": "https://b"}},
    ]
    results = [
        ToolCallResult("b", 1, {"ok": True, "title": "B"}),
        ToolCallResult("a", 0, {"ok": True, "title": "A"}),
    ]
    messages = build_tool_messages(calls, results)
    assert [message.tool_call_id for message in messages] == ["a", "b"]
```

Use existing compression fixtures where possible. Do not introduce a fake search provider as an acceptance test.

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```powershell
uv run pytest tests/orchestration/test_tool_executor.py tests/context/test_compression.py -v
```

- [ ] **Step 3: Add task fields through the compression path**

```python
@dataclass(frozen=True, slots=True)
class CompressionRequest:
    tool_call_id: str
    order: int
    document: RawDocument
    selection: ChunkSelection
    active_query: str
    task_id: str
    section_id: str
```

Every compressed, irrelevant and extractive-fallback `ResearchNote` must copy these fields. Include task identity in note ID generation so the same page can safely produce different task notes.

Use this exact extractive fallback signature:

```python
def build_extractive_note(
    document: RawDocument,
    selection: ChunkSelection,
    active_query: str,
    task_id: str,
    section_id: str,
    error: str,
) -> ResearchNote:
    snippets = [chunk.text for chunk in selection.chunks if chunk.text.strip()]
    return ResearchNote(
        note_id=_note_id(document.doc_id, active_query, task_id),
        doc_id=document.doc_id,
        task_id=task_id,
        section_id=section_id,
        active_query=active_query,
        title=document.title or document.final_url,
        key_points=snippets[:3] or ["未提取到相关正文"],
        evidence_snippets=snippets or ["未提取到相关正文"],
        source_url=document.final_url,
        relevance_score=selection.top1_fused_score,
        compression_status="extractive_fallback",
        error=error,
    )
```

- [ ] **Step 4: Move external tool execution out of ResearchNodes**

Move the current search, fetch, chunk, embedding, selection, compression, cache reuse and ToolMessage fan-in logic into `ResearchToolExecutor`. Keep these properties:

- Search responses remain short candidate lists.
- Before each search, compare the normalized query with the current
  `TaskCoverage.attempted_queries` using exact matching and
  `is_repeated_query(runtime, query, coverage.attempted_queries,
  settings.query_loop_threshold)`; return a structured `duplicate_query`
  result instead of calling Tavily when repeated.
- Record every accepted query in the current task coverage, not in one global
  history shared by unrelated tasks.
- Fetches in the same AI response use `asyncio.gather`.
- New chunks are embedded in one batch.
- Compression uses existing bounded `compress_many`.
- Existing pages reuse document, chunks and vectors but generate a new task-specific note when required.
- Completion tool calls are rejected by this executor because routing handles them separately.

`ToolExecutionUpdate` is a Pydantic model or frozen dataclass with an `as_state_update() -> dict[str, Any]` method; do not return an undocumented tuple.

- [ ] **Step 5: Reduce orchestration/nodes.py to delegation**

Remove copied tool implementation after `ResearchToolExecutor` is used. Keep pure message-order helpers in `tool_executor.py` and re-export them only if existing tests or public imports need them.

- [ ] **Step 6: Run focused and stage 2 regression tests**

Run:

```powershell
uv run pytest tests/context tests/tools tests/orchestration/test_tool_executor.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```powershell
git add backend/src/deeptrace/context/compression.py backend/src/deeptrace/models/document.py backend/src/deeptrace/orchestration/tool_executor.py backend/src/deeptrace/orchestration/nodes.py backend/tests/context/test_compression.py backend/tests/orchestration/test_tool_executor.py
git commit -m "refactor: extract task-aware research tool executor"
```

---

### Task 5: Writer、实际使用来源与降级报告

**Files:**
- Create: `backend/src/deeptrace/prompts/writer.py`
- Create: `backend/src/deeptrace/agent/writer.py`
- Test: `backend/tests/agent/test_writer.py`

**Interfaces:**
- Produces: `WriterOutput(markdown: str, used_note_ids: list[str])`
- Produces: `render_fallback_report(plan: ResearchPlan, sections: Sequence[SectionResult], notes: Sequence[ResearchNote], termination_reason: str) -> WriterOutput`
- Produces: `WriterAgent.awrite` with the exact signature below, returning `tuple[WriterOutput, TokenUsage, bool]`; final bool is `used_fallback`.
- Consumes: plan, ordered section results, referenced ResearchNotes and termination reason.
- Writer never consumes `RawDocument`, search result payloads or external tools.

- [ ] **Step 1: Write deterministic Writer tests**

```python
from deeptrace.agent.writer import render_fallback_report
from deeptrace.prompts.writer import build_writer_messages


def test_writer_messages_do_not_contain_raw_document(
    research_plan, section_result, research_note
) -> None:
    messages = build_writer_messages(
        plan=research_plan,
        sections=[section_result],
        notes=[research_note],
        termination_reason="completed",
    )
    text = "\n".join(str(message.content) for message in messages)
    assert research_note.key_points[0] in text
    assert "整页正文唯一标记" not in text


def test_fallback_report_discloses_partial_sections(
    research_plan, partial_section, research_note
) -> None:
    output = render_fallback_report(
        research_plan, [partial_section], [research_note], "token_budget"
    )
    assert "部分完成" in output.markdown
    assert "token_budget" in output.markdown
    assert output.used_note_ids == [research_note.note_id]
```

- [ ] **Step 2: Run Writer tests and confirm failure**

Run: `uv run pytest tests/agent/test_writer.py -v`

- [ ] **Step 3: Implement Writer prompt**

`build_writer_messages` serializes only these fields:

- plan objective, time range and outline;
- section title, summary, coverage, errors and note IDs;
- selected note title, key points, evidence snippets and source URL;
- termination reason and the statement that Claim-level verification is not implemented.

The prompt requires a structured result:

```python
class WriterOutput(BaseModel):
    markdown: str = Field(min_length=1)
    used_note_ids: list[str] = Field(default_factory=list)
```

It must require Executive Summary, planned sections, limitations and references when supported, while prohibiting facts absent from notes.

- [ ] **Step 4: Implement WriterAgent and deterministic fallback**

```python
class WriterAgent:
    def __init__(self, model: Any) -> None:
        self._structured_model = model.with_structured_output(
            WriterOutput, include_raw=True
        )

    async def awrite(
        self,
        *,
        plan: ResearchPlan,
        sections: Sequence[SectionResult],
        notes: Sequence[ResearchNote],
        termination_reason: str,
    ) -> tuple[WriterOutput, TokenUsage, bool]:
        messages = build_writer_messages(
            plan=plan, sections=sections, notes=notes,
            termination_reason=termination_reason,
        )
        total = TokenUsage()
        allowed_ids = {note.note_id for note in notes}
        for _attempt in range(2):
            try:
                result = await self._structured_model.ainvoke(messages)
                total = add_usage(total, message_usage(result.get("raw")))
                parsed = result.get("parsed")
                if isinstance(parsed, WriterOutput):
                    clean = parsed.model_copy(update={
                        "used_note_ids": [
                            item for item in parsed.used_note_ids
                            if item in allowed_ids
                        ]
                    })
                    return clean, total, False
            except Exception:
                continue
        return (
            render_fallback_report(plan, sections, notes, termination_reason),
            total,
            True,
        )
```

Retry once on model/parse failure. Filter `used_note_ids` to IDs actually supplied to Writer. If both attempts fail, return `render_fallback_report`; do not discard completed sections.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest tests/agent/test_writer.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```powershell
git add backend/src/deeptrace/agent/writer.py backend/src/deeptrace/prompts/writer.py backend/tests/agent/test_writer.py
git commit -m "feat: add bounded research report writer"
```

---

### Task 6: 任务覆盖、预算和 LangGraph 拓扑

**Files:**
- Create: `backend/src/deeptrace/orchestration/coverage.py`
- Create: `backend/src/deeptrace/orchestration/budget.py`
- Modify: `backend/src/deeptrace/orchestration/nodes.py`
- Modify: `backend/src/deeptrace/orchestration/graph.py`
- Modify: `backend/src/deeptrace/orchestration/__init__.py`
- Modify: `backend/src/deeptrace/orchestration/state.py`
- Test: `backend/tests/orchestration/test_coverage.py`
- Modify Test: `backend/tests/orchestration/test_graph.py`

**Interfaces:**
- Produces: `complete_coverage(task, previous, completion, notes, errors) -> TaskCoverage`
- Produces: `forced_coverage(task, previous, notes, reason) -> TaskCoverage`
- Produces: `get_budget_reason(state: GraphState, settings: Settings, now: datetime) -> str | None`
- Produces: `ResearchWorkflowNodes` methods `plan_node`, `start_task_node`, `research_node`, `tools_node`, `complete_task_node`, `writer_node`
- Produces routes: `route_after_research` and `route_after_task`
- Produces: `build_research_graph() -> CompiledStateGraph`

- [ ] **Step 1: Write coverage and routing tests**

```python
from deeptrace.orchestration.coverage import complete_coverage, forced_coverage
from deeptrace.orchestration.graph import route_after_research, route_after_task


def test_completion_is_sufficient_only_with_sources_note_and_no_gaps(
    research_task, running_coverage, task_completion, research_note
) -> None:
    coverage = running_coverage.model_copy(update={
        "successful_source_urls": ["https://a", "https://b"],
        "relevant_note_ids": [research_note.note_id],
    })
    result = complete_coverage(
        research_task, coverage, task_completion, [research_note], []
    )
    assert result.status == "sufficient"


def test_budget_forces_partial_when_a_note_exists(
    research_task, running_coverage, research_note
) -> None:
    result = forced_coverage(
        research_task, running_coverage, [research_note], "task_round_budget"
    )
    assert result.status == "partial"
    assert result.failure_reason == "task_round_budget"


def test_research_route_distinguishes_external_and_completion_calls() -> None:
    search = AIMessage(content="", tool_calls=[{
        "id": "search-1", "name": "search_web",
        "args": {"query": "AI Agent"}, "type": "tool_call",
    }])
    completion = AIMessage(content="", tool_calls=[{
        "id": "done-1", "name": "complete_research_task",
        "args": {
            "task_id": "task-01", "summary": "完成",
            "covered_topics": [], "unresolved_topics": [],
        },
        "type": "tool_call",
    }])
    assert route_after_research({
        "messages": [search], "pending_task_completion": None,
    }) == "tools"
    assert route_after_research({
        "messages": [completion], "pending_task_completion": None,
    }) == "complete_task"
    assert route_after_research({
        "messages": [], "pending_task_completion": TaskCompletion(
            task_id="task-01", summary="预算结束"
        ),
    }) == "complete_task"
```

- [ ] **Step 2: Run new tests and confirm failure**

Run:

```powershell
uv run pytest tests/orchestration/test_coverage.py tests/orchestration/test_graph.py -v
```

- [ ] **Step 3: Implement deterministic coverage and budget policies**

`complete_coverage` marks:

- `sufficient`: distinct sources meet `min_sources`, at least one relevant note, no unresolved topics;
- `partial`: useful note exists but source/topic/round/empty-query condition is incomplete;
- `failed`: no relevant note exists.

`get_budget_reason` checks in this order:

```python
def get_budget_reason(state, settings, now):
    if state.get("force_finalize"):
        return "forced_finalize"
    if state["step_count"] >= settings.hard_max_steps:
        return "step_budget"
    if state["fetched_page_count"] >= settings.max_fetched_pages:
        return "page_budget"
    if state["api_token_count"] >= settings.max_api_tokens:
        return "token_budget"
    if (
        settings.max_cost_usd is not None
        and Decimal(str(state["estimated_cost_usd"])) >= settings.max_cost_usd
    ):
        return "cost_budget"
    if elapsed_seconds(state["started_at"], now) >= settings.max_runtime_seconds:
        return "time_budget"
    return None
```

Task round limit and two consecutive empty rounds are checked before invoking Researcher.

- [ ] **Step 4: Implement thin workflow nodes**

`ResearchWorkflowNodes` receives PlannerAgent, ResearcherAgent, WriterAgent, ResearchToolExecutor, settings, runtime and event callback. Node responsibilities:

- `plan_node`: create plan, initialize coverage for every task, add planning events and usage.
- `start_task_node`: select by index, mark running and clear old task messages.
- `research_node`: check deterministic budgets, retrieve notes using user + task query, or call Researcher.
- `tools_node`: delegate external calls and update current coverage counters.
- `complete_task_node`: parse completion or force partial/failed, create `SectionResult`, increment index.
- `writer_node`: call Writer once, store final answer and `used_note_ids`.

No node may reimplement fetch, compression or report rendering.

- [ ] **Step 5: Replace graph topology**

```python
workflow.add_edge(START, "plan")
workflow.add_edge("plan", "start_task")
workflow.add_edge("start_task", "research")
workflow.add_conditional_edges(
    "research",
    route_after_research,
    {"tools": "tools", "complete_task": "complete_task"},
)
workflow.add_edge("tools", "research")
workflow.add_conditional_edges(
    "complete_task",
    route_after_task,
    {"start_task": "start_task", "writer": "writer"},
)
workflow.add_edge("writer", END)
```

The graph must have no direct Researcher-to-END route.

- [ ] **Step 6: Run orchestration tests**

Run:

```powershell
uv run pytest tests/orchestration -v
```

Expected: PASS, including existing tool-order and state reducer guarantees after updated assertions.

- [ ] **Step 7: Commit Task 6**

```powershell
git add backend/src/deeptrace/orchestration backend/tests/orchestration
git commit -m "feat: orchestrate planned research tasks"
```

---

### Task 7: 配置、依赖组装、结果对象和 CLI

**Files:**
- Modify: `backend/src/deeptrace/config/settings.py`
- Modify: `backend/src/deeptrace/observability/token_metrics.py`
- Modify: `backend/src/deeptrace/observability/__init__.py`
- Modify: `backend/src/deeptrace/agent/service.py`
- Modify: `backend/src/deeptrace/agent/__init__.py`
- Modify: `backend/src/deeptrace/__init__.py`
- Modify: `backend/src/deeptrace/cli.py`
- Modify: `backend/.env.example` if it exists; otherwise create it without credentials
- Modify Test: `backend/tests/config/test_settings.py`
- Test: `backend/tests/agent/test_service.py`
- Test: `backend/tests/test_cli.py`

**Interfaces:**
- Changes: `build_real_agent(settings: Settings, on_event: Callable[[RunEvent], None] | None = None) -> ResearchAgent`
- Changes: `AgentResult` adds `plan`, ordered `sections`, structured `events`, `used_note_ids` and total provider usage.
- Produces: `estimate_usage_cost(usage: TokenUsage, input_price: Decimal | None, output_price: Decimal | None) -> Decimal | None`.
- Sources are derived only from `used_note_ids`, never all fetched documents.
- CLI prints `RunEvent.message` and preserves the existing final answer, sources, status and Token summary.

- [ ] **Step 1: Add Settings boundary tests**

```python
def test_stage3_budget_defaults(monkeypatch, tmp_path) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("DEEPTRACE_EMBEDDING_MODEL_PATH", str(tmp_path))
    settings = Settings.from_env()
    assert settings.max_research_tasks == 4
    assert settings.max_task_rounds == 3
    assert settings.min_sources_per_task == 2
    assert settings.max_fetched_pages == 20
    assert settings.max_runtime_seconds == 600
    assert settings.max_api_tokens == 120_000


def test_cost_limit_requires_pricing(monkeypatch, tmp_path) -> None:
    _set_required_environment(monkeypatch)
    monkeypatch.setenv("DEEPTRACE_EMBEDDING_MODEL_PATH", str(tmp_path))
    monkeypatch.setenv("DEEPTRACE_MAX_COST_USD", "1.00")
    with pytest.raises(RuntimeError, match="模型单价"):
        Settings.from_env()
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```powershell
uv run pytest tests/config/test_settings.py tests/agent/test_service.py tests/test_cli.py -v
```

- [ ] **Step 3: Add exact stage 3 settings**

Add and validate:

```python
max_research_tasks: int = 4
max_task_rounds: int = 3
min_sources_per_task: int = 2
max_fetched_pages: int = 20
max_runtime_seconds: int = 600
max_api_tokens: int = 120_000
input_cost_per_million: Decimal | None = None
output_cost_per_million: Decimal | None = None
max_cost_usd: Decimal | None = None
```

Environment variables use the same uppercase names prefixed with `DEEPTRACE_`. If a cost cap is set without both prices, raise a configuration error. Never ship provider prices as guessed defaults.

Implement cost calculation without floats:

```python
def estimate_usage_cost(
    usage: TokenUsage,
    input_price: Decimal | None,
    output_price: Decimal | None,
) -> Decimal | None:
    if input_price is None or output_price is None:
        return None
    million = Decimal(1_000_000)
    return (
        Decimal(usage.input_tokens) * input_price
        + Decimal(usage.output_tokens) * output_price
    ) / million
```

Planner, Researcher, Writer and compression usage all increment
`api_token_count`. They increment `estimated_cost_usd` only when this
function returns a value; otherwise CLI displays cost as `unavailable`.

- [ ] **Step 4: Assemble real dependencies**

`build_real_agent` must:

1. construct one unbound ChatOpenAI model;
2. pass it to PlannerAgent and WriterAgent;
3. let ResearcherAgent bind `RESEARCHER_TOOL_SCHEMAS`;
4. build the existing CompressionRuntime, CompressionService and AsyncWebFetcher;
5. build ResearchToolExecutor and ResearchWorkflowNodes;
6. compile the new graph;
7. keep `ResearchAgent.aclose()` closing the fetcher.

Initialize every required GraphState key explicitly in `ResearchAgent.arun`, including ISO UTC `started_at`, plan/task fields, counters and structured events.

- [ ] **Step 5: Correct AgentResult source selection**

```python
used = set(final.get("used_note_ids", []))
notes = final.get("notes", {})
sources = list(dict.fromkeys(
    note.source_url
    for note_id, note in notes.items()
    if note_id in used
))
```

Do not sort away Writer/report order unless duplicates require removal. If Writer fallback is used, its `used_note_ids` determine sources the same way.

- [ ] **Step 6: Update CLI and essential tests**

CLI description becomes “DeepTrace 规划式深度研究 Agent”. Its callback accepts `RunEvent`:

```python
def _print_event(event: RunEvent) -> None:
    print(event.message)
```

Test argument parsing, exit status mapping and event formatting as pure logic. Do not patch in a fake complete external research run.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
uv run pytest tests/config/test_settings.py tests/agent/test_service.py tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 7**

```powershell
git add backend/src/deeptrace/config backend/src/deeptrace/observability backend/src/deeptrace/agent backend/src/deeptrace/__init__.py backend/src/deeptrace/cli.py backend/.env.example backend/tests/config/test_settings.py backend/tests/agent/test_service.py backend/tests/test_cli.py
git commit -m "feat: integrate planned research application"
```

---

### Task 8: 全量回归、真实冒烟和交接收尾

**Files:**
- Modify: `backend/README.md`
- Modify: `docs/README.md`
- Modify: `docs/roadmap/deeptrace-evolution.md`
- Modify: `docs/superpowers/specs/2026-09-01-stage-03-planned-deep-research-design.md` only if implementation required an explicitly documented deviation

**Interfaces:**
- No new production interface.
- Delivers a runnable stage 3 system and updates documentation to match actual code.

- [ ] **Step 1: Run the complete automated suite**

Run:

```powershell
cd backend
uv run pytest -m "not real"
uv run python -m compileall src
```

Expected: all tests PASS and compileall exits 0.

Do not spend time on unrelated lint, benchmark or broad code review. Fix only regressions caused by stage 3.

- [ ] **Step 2: Inspect graph topology and package imports**

Run:

```powershell
uv run python -c "from deeptrace.orchestration import build_research_graph; print(build_research_graph().get_graph().nodes.keys())"
uv run python -c "from deeptrace import build_real_agent; from deeptrace.models import ResearchPlan, SectionResult; print('imports-ok')"
```

Expected graph nodes:

```text
plan, start_task, research, tools, complete_task, writer
```

- [ ] **Step 3: Run one real end-to-end smoke test**

With the user's real `.env` and local `D:\Dev\Models\bge-m3`:

```powershell
uv run deeptrace "2024年AI Agent领域有哪些重要进展？"
```

Confirm from the actual output:

- a plan appears before search;
- at least two distinct tasks execute;
- search and fetch use real external services;
- the report follows the plan and marks partial/failed sections;
- sources correspond to Writer-used notes rather than every fetched page;
- report states that stage 3 has no Claim-level verification;
- there is no unhandled exception;
- Token usage is still printed.

If an external site or provider fails, preserve the real failure reason and retry only the affected smoke once. Do not replace it with static data.

- [ ] **Step 4: Update documentation from actual behavior**

`backend/README.md` must contain:

- stage 3 directory tree;
- Planner → Researcher/Tools → Writer flow;
- new environment variables and defaults;
- run and test commands;
- stage 3 reliability limitation.

`docs/README.md` must link this implementation plan and mark it as the current execution source. After successful smoke, update roadmap status to “阶段 1、2、3 已完成，阶段 4 待开始” and current-next-step to stage 4. Do not mark complete before the real smoke succeeds.

- [ ] **Step 5: Check secrets and diff scope**

Run:

```powershell
git status --short
git diff --check
git diff --name-only
git grep -n -I -E "sk-[A-Za-z0-9_-]{12,}|TAVILY_API_KEY=.*[^=[:space:]]" -- . ":(exclude)backend/.env"
```

Expected: no secret values; only intended stage 3 code, tests and docs are part of this task. Preserve pre-existing unrelated dirty files.

- [ ] **Step 6: Commit Task 8**

```powershell
git add backend/README.md docs/README.md docs/roadmap/deeptrace-evolution.md docs/superpowers/specs/2026-09-01-stage-03-planned-deep-research-design.md
git commit -m "docs: complete planned deep research stage"
```

If the spec did not change, omit it from `git add`.

## Final Acceptance

- [ ] Planner creates a bounded, structured and time-aware research plan.
- [ ] Researcher operates on one task at a time and explicitly completes it.
- [ ] Multiple external tool calls preserve `tool_call_id` mapping.
- [ ] ResearchNote records task and section ownership.
- [ ] Task switching clears unrelated tool history.
- [ ] Writer sees only plan, SectionResult and ResearchNote data.
- [ ] Final sources come only from Writer-used note IDs.
- [ ] Task and global budgets have deterministic termination paths.
- [ ] Partial task failures still produce an honest report.
- [ ] Existing context compression and scraper fallback still work.
- [ ] Automated suite and one real API smoke run pass.
- [ ] No stage 4–6 modules or empty directories were added.
