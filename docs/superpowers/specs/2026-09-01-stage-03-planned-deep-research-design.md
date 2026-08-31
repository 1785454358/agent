# 阶段 3 规划式 Deep Research 设计

- 状态：待实施
- 日期：2026-09-01
- 前置阶段：阶段 2 已完成
- 路线图：[DeepTrace 演进路线图](../../roadmap/deeptrace-evolution.md)
- 总体架构：[DeepTrace 总体目标架构](../../architecture/deeptrace-target-architecture.md)

## 1. 目标

在阶段 2 的可靠搜索、并发抓取、BGE-M3 召回和上下文压缩基础上，将单 Agent 循环升级为 Planner、Researcher、Writer 分工明确的规划式 Deep Research。

阶段 3 完成后，一个宽泛问题应先形成结构化计划，再逐项研究，最后根据各部分研究结果统一写作。系统吸收 GPT Researcher 的规划、多查询、批量抓取、按子问题召回和研究/写作分离能力，同时保留明确预算与失败状态。

## 2. 本阶段边界

### 包含

- 问题规范化、语言和时间范围提取。
- 结构化研究计划及 2 至 5 个互补子任务。
- Planner、Researcher、Writer 独立角色服务。
- 单个 LangGraph 中的任务调度、工具循环和统一写作。
- 子任务查询扩展、查询去重、批量抓取和 BGE-M3 双查询召回。
- 基于笔记、来源和预期主题的基础覆盖状态。
- 子任务轮数、全局步骤、网页数、运行时间和 Token 预算。
- 结构化运行事件、部分报告和失败原因。
- 真实 API 冒烟验证。

### 不包含

- `Source → Evidence → Claim` 数据链。
- Claim 级引用、来源权威性评分和 Verifier。
- 根据 Claim 缺口进行补搜。
- 长期 Memory、数据库、checkpoint、FastAPI 和 Web UI。
- MCP 或更多搜索引擎适配器。
- 固定评测集、消融和开源项目正式对比。

阶段 3 的报告只能说明“基于抓取后研究笔记生成”，不能宣称事实已经通过 Claim 级验证。

## 3. 实现方案

采用单个 LangGraph 拆分角色节点，不在本阶段引入嵌套子图或多 Researcher 并行。

```text
START
  ↓
plan_research
  ↓
start_task
  ↓
research_task ←─────────────┐
  ├── search/fetch tools ───┘
  ├── complete_task
  └── task budget reached
           ↓
     advance_task
       ├── 仍有任务 → start_task
       └── 全部结束 → write_report
                            ↓
                           END
```

子任务在阶段 3 串行执行。网页抓取和同一轮压缩继续使用阶段 2 的有界并发。阶段 4 可以在此图中插入 Evidence 与 Verifier；后续如确有收益，Researcher 可以替换为子图而不改变角色接口。

## 4. 数据模型

新增模型统一放在 `models/`，使用 Pydantic 并保持可序列化。

### ResearchTimeRange

```python
class ResearchTimeRange(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    description: str = ""
```

绝对日期优先；无法可靠解析时保留用户原始描述，不猜测日期。

### ResearchTask

```python
class ResearchTask(BaseModel):
    task_id: str
    section_id: str
    title: str
    question: str
    planned_queries: list[str]
    expected_topics: list[str]
    min_sources: int
```

- `task_id` 和 `section_id` 由 Planner 服务生成稳定 ID，不让模型自由生成。
- 每个任务保留 1 至 3 条去重后的初始查询。
- `expected_topics` 用于阶段 3 的基础覆盖提示，不代表已经形成 Claim。

### ResearchPlan

```python
class ResearchPlan(BaseModel):
    plan_id: str
    original_query: str
    normalized_query: str
    objective: str
    language: str
    time_range: ResearchTimeRange | None
    tasks: list[ResearchTask]
    report_outline: list[str]
```

默认最多 4 个任务，配置允许的硬上限为 5。任务必须覆盖不同研究维度，不能只是同一句问题的改写。

### TaskCoverage

```python
TaskStatus = Literal["pending", "running", "sufficient", "partial", "failed"]

class TaskCoverage(BaseModel):
    task_id: str
    status: TaskStatus
    attempted_queries: list[str]
    successful_source_urls: list[str]
    relevant_note_ids: list[str]
    covered_topics: list[str]
    missing_topics: list[str]
    rounds: int
    consecutive_empty_rounds: int
    failure_reason: str | None = None
```

`sufficient` 是阶段 3 的流程判断，只说明满足基础来源和主题条件，不等价于事实验证通过。

### SectionResult

```python
class SectionResult(BaseModel):
    task_id: str
    section_id: str
    title: str
    summary: str
    note_ids: list[str]
    source_urls: list[str]
    coverage: TaskCoverage
    errors: list[str]
```

Writer 消费 `SectionResult` 和相关 `ResearchNote`，不消费 `RawDocument.content`。

### RunEvent

```python
class RunEvent(BaseModel):
    event_type: str
    message: str
    task_id: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )
```

阶段 3 至少产生规划、任务开始、搜索、抓取、压缩、任务结束、预算终止、写作和完成事件。CLI 输出 `message`；阶段 5 可以直接把结构化事件转为 SSE。

### ResearchNote 调整

`ResearchNote` 增加 `task_id` 和 `section_id`。同一网页针对不同子任务可以生成不同笔记；正文、chunks 和进程内向量继续复用。

## 5. 角色职责

### Planner

输入用户原始问题和当前日期，输出结构化计划。

职责：

- 折叠异常空白并生成 `normalized_query`。
- 解析显式年份和“今天、最新、今年”等相对时间。
- 拆成互补研究维度，默认 3 至 4 个，最多 5 个。
- 每个任务生成 1 至 3 条初始查询、预期主题和最低来源数。
- 生成报告章节顺序。

Planner 使用模型结构化输出。解析失败时重试一次；仍失败则创建只包含原问题的单任务降级计划，并记录 `planning.fallback`，保证系统仍可工作。

### Researcher

一次只研究当前 `ResearchTask`。

职责：

- 读取当前任务、该任务的查询历史和相关研究笔记。
- 优先执行尚未尝试的计划查询，再根据缺口生成新查询。
- 一次模型响应可以调用多个搜索或抓取工具。
- 调用内部 `complete_research_task` 工具明确结束任务，返回摘要、覆盖主题和缺口。
- 不生成最终报告，不评价 Claim 是否已经验证。

Researcher 的提示上下文只包含用户问题、当前任务、当前任务相关笔记、最近完整工具回合和预算摘要。切换任务时清空上一任务的工具消息。

### Writer

只在全部任务结束或全局预算触发后运行一次。

职责：

- 按 `ResearchPlan.report_outline` 组织摘要和正文。
- 使用各 `SectionResult` 及其研究笔记。
- 明确标出 `partial`、`failed` 和缺少来源的部分。
- 输出摘要、分层正文、必要对比表、局限说明和实际使用的来源。
- 不调用搜索、抓取或其他工具。
- 不使用未出现在输入笔记中的事实。

Writer 调用失败时重试一次；仍失败则由确定性 Markdown 渲染器根据 `SectionResult` 输出部分报告，不丢失已完成研究。

## 6. 查询、抓取与覆盖

### 查询规范化与去重

- 折叠空白、去除首尾标点噪声并统一可安全统一的大小写。
- 文本完全相同的查询直接去重。
- 新查询与当前任务历史查询使用 BGE-M3 计算相似度，最大值高于 `0.85` 时视为循环，不再执行。
- 查询必须继承任务时间范围；相对时间转换为包含明确日期或年份的搜索词。

### 批量工具执行

- 同一 Researcher 响应中的搜索调用形成一批，结果按 `tool_call_id` 回填。
- 同一响应中的网页抓取继续使用 `asyncio.gather` 有界并发。
- URL 先规范化和去重；已经抓取的页面复用正文、chunks 和向量。
- 每个结果独立失败，不取消同批其他调用。

### 基础覆盖规则

任务满足以下条件时可以标记 `sufficient`：

1. 不同成功来源数达到 `min_sources`。
2. 至少形成一条非 `irrelevant` 研究笔记。
3. Researcher 没有报告未覆盖主题。

达到任务轮数上限、连续两轮没有新增笔记或剩余查询都被判定重复时，任务结束为 `partial`。所有抓取失败且没有研究笔记时标记 `failed`。

这是流程覆盖，不是证据质量判定；阶段 4 将使用 Claim 和 Verifier 替换其可靠性部分。

## 7. 预算与停止

保留阶段 2 的全局软、硬步骤限制，并新增：

- `DEEPTRACE_MAX_RESEARCH_TASKS=4`
- `DEEPTRACE_MAX_TASK_ROUNDS=3`
- `DEEPTRACE_MIN_SOURCES_PER_TASK=2`
- `DEEPTRACE_MAX_FETCHED_PAGES=20`
- `DEEPTRACE_MAX_RUNTIME_SECONDS=600`
- `DEEPTRACE_MAX_API_TOKENS=120000`

模型费用只有在配置输入、输出单价时才计算并允许设置费用上限；OpenAI-compatible Provider 价格未知时显示 `unavailable`，不能猜测。

停止优先级：

1. 用户或系统取消。
2. 全局硬预算。
3. 当前任务预算或连续无新增。
4. 当前任务达到基础覆盖。
5. 全部任务结束后写作。

预算触发不会丢弃已完成任务，Writer 生成带停止原因的部分报告。

## 8. State 与 reducer

`GraphState` 新增：

```python
research_plan: ResearchPlan | None
current_task_index: int
task_coverages: Annotated[dict[str, TaskCoverage], merge_dicts]
section_results: Annotated[dict[str, SectionResult], merge_dicts]
events: Annotated[list[RunEvent], operator.add]
started_at: str
fetched_page_count: int
api_token_count: int
```

现有 documents、chunks、notes 和查询历史继续使用 reducer。查询历史应按任务隔离，不能用一个全局列表阻止不同任务的合理查询。向量仍不进入 State。

## 9. 文件边界

### 新增

- `models/plan.py`：时间范围、研究计划和任务。
- `models/report.py`：覆盖状态、章节结果和运行事件。
- `agent/planner.py`：Planner 结构化输出、规范化与降级。
- `agent/researcher.py`：当前任务的模型决策和完成协议。
- `agent/writer.py`：统一报告写作和确定性降级渲染。
- `prompts/planner.py`、`prompts/researcher.py`、`prompts/writer.py`：角色提示词。
- `orchestration/tool_executor.py`：从现有节点抽出的搜索、抓取、分块、召回和压缩执行。

### 修改

- `models/research.py`：ResearchNote 增加任务归属。
- `models/__init__.py`：导出新增公共模型。
- `config/settings.py`：阶段 3 预算配置。
- `orchestration/state.py`：阶段 3 状态和 reducer。
- `orchestration/nodes.py`：改为调用角色服务与工具执行器的轻量节点集合。
- `orchestration/graph.py`：替换为规划、逐任务研究和写作拓扑。
- `agent/service.py`：组装角色、执行器和图，返回计划与章节状态。
- `cli.py`：展示结构化阶段事件及最终研究状态。
- `backend/README.md`：更新阶段 3 流程、模块和运行说明。

不创建 `evidence/`、`verification/`、`memory/` 或 API 目录。

## 10. 错误处理

- Planner 结构化输出失败：重试一次，再使用单任务降级计划。
- 单次搜索或抓取失败：保存错误，其他同批结果继续。
- 压缩失败：沿用阶段 2 的 JSON 修复、重试和抽取式降级。
- Researcher 未调用工具也未完成任务：允许一次纠正提示，再把任务标记为 `partial`。
- 单个任务失败：继续后续任务，Writer 明确披露。
- Writer 失败：重试一次，再使用确定性 Markdown 降级。
- 全局预算触发：停止新工具调用，保留已有结果并写部分报告。
- 任何日志和事件都不得包含 API Key、Cookie 或完整敏感请求头。

## 11. 验证策略

只做保证阶段 3 正常工作的必要验证，不做大规模评测。

### 自动化测试

- Pydantic 模型边界和 reducer。
- 问题空白规范化、任务数限制和查询去重。
- Planner 无效输出的单任务降级。
- 路由在外部工具、完成任务、下一任务和 Writer 之间正确切换。
- 并发工具结果始终按 `tool_call_id` 回填。
- 任务达到来源条件、空轮或预算时状态正确。
- 切换任务后不携带上一任务工具消息。
- Writer 输入不包含 `RawDocument.content`。
- 预算终止仍能生成部分报告。

自动化测试只测试纯模型、路由和确定性逻辑，不伪造外部搜索结果或模型答案作为验收。

### 真实冒烟

使用真实 LLM、Tavily 和网页抓取运行：

```powershell
uv run deeptrace "2024年AI Agent领域有哪些重要进展？"
```

验收时确认：

- CLI 先显示研究计划，再显示各子任务执行过程。
- 至少两个不同子任务完成真实搜索和抓取。
- 主上下文中不存在整页正文。
- 最终报告按计划组织，并披露证据不足与阶段 3 未做 Claim 级验证。
- 运行结束无未处理异常，Token 统计仍可用。

## 12. 完成定义

1. 阶段 2 的真实搜索、可靠抓取和压缩能力没有回退。
2. Planner、Researcher、Writer 边界可从代码和文档直接解释。
3. 结构化计划能够驱动多个子任务依次完成。
4. 查询循环、任务空转和全局预算都有确定性停止路径。
5. 部分失败不会阻止其余任务和最终报告。
6. 必要自动化测试与一次真实冒烟通过。
7. 没有提前实现阶段 4 至阶段 6 的功能。
