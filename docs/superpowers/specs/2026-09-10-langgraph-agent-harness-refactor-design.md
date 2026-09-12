# ResearchPilot LangGraph Agent Harness 重构设计

## 1. 背景

ResearchPilot 当前提供 Basic、Deep 和 Multi-Agent 三种研究模式，也提供 Local 与 Distributed 两种部署运行方式。部署层已经通过统一的运行接口隔离 API、Worker、MySQL 和 Redis，但研究层仍由三套相对独立的实现承担模型装配、资源生命周期、额度、事件、工具调用和结果收尾。

现有三种研究模式分别是：

- Basic：固定的 Planner、并行搜索抓取和 Writer 工作流。
- Deep：由 Python 循环实现的 Plan-and-Execute、工具执行和重规划。
- Multi-Agent：由 LangGraph 编排 Supervisor 和多个 Researcher。

这种结构验证了三种研究策略的可行性，但相同的运行治理能力被分散在模式目录中。新增策略时仍需重新实现模型、工具、额度、事件、缓存、Writer 和资源关闭，也无法统一支持多轮会话、节点级恢复和长期记忆生命周期。

本次重构允许重新定义三种模式的执行行为，不要求保持原内部实现兼容。对外仍保留三种显式可选研究模式，后续在有评测依据后再增加 Auto Mode。

## 2. 目标

本次重构建立一套基于 LangGraph 的模块化 Research Agent Harness，并实现以下目标：

1. 使用 LangGraph 统一所有 Agent 编排，不再保留手写研究循环。
2. 通过顶层运行图和研究策略子图区分通用执行治理与研究策略。
3. 保留三种显式研究模式，并统一更名为 Workflow、Plan-and-Execute 和 Multi-Agent。
4. 支持同一会话持续追问、增量研究和模式切换。
5. 默认输出简洁自然的回答，只有用户明确要求时才生成正式报告。
6. 实现滑动窗口与结构化动态压缩组成的短期记忆。
7. 实现长期记忆的存储、组织、召回、更新和遗忘生命周期。
8. 统一工具权限、参数校验、额度、缓存、超时、重试、幂等性和证据入库。
9. 使用持久化 Checkpoint 支持节点级暂停、恢复和 Human-in-the-loop。
10. 建立能够比较三种研究模式质量、成本、延迟和可靠性的评测体系。

## 3. 非目标

第一版不实现以下能力：

- Auto Mode 路由。
- Agent 自动修改系统 Prompt 或程序规则。
- Researcher 递归创建新的子 Agent。
- 不受策略控制的长期记忆写入工具。
- 跨用户共享私人记忆。
- 无证据支持的事实或经验自动学习。
- Exactly-once 分布式执行承诺。
- 自建编排框架取代 LangGraph。
- 强制依赖 LangGraph Agent Server、LangSmith Cloud 或其他托管服务。

## 4. 术语与命名

### 4.1 两个正交维度

研究策略和部署运行方式是两个独立维度：

| 维度 | 类型 | 职责 |
| --- | --- | --- |
| Research Mode | Workflow、Plan-and-Execute、Multi-Agent | 用户选择的研究模式，决定如何规划、研究、评估和补查 |
| Deployment Runtime | Local、Distributed | 决定任务在哪里执行、如何排队、持久化和取消 |

### 4.2 研究模式更名

| 旧标识 | 新标识 | 展示名称 |
| --- | --- | --- |
| `basic` | `workflow` | Workflow |
| `deep` | `plan_execute` | Plan-and-Execute |
| `multi_agent` | `multi_agent` | Multi-Agent |

新代码采用 `WorkflowResearchGraph`、`PlanExecuteResearchGraph` 和 `MultiAgentResearchGraph`。旧标识只用于读取或迁移历史数据，不作为新 API 的公开值。

### 4.3 Harness、Mode 与 Strategy

Agent Harness 负责每一次运行如何被治理，包括上下文、工具、资源、额度、事件、持久化、恢复和结果契约。`ResearchMode` 是用户与 API 选择的模式标识，`ResearchStrategyGraph` 是模式对应的策略子图接口。LangGraph 是顶层运行图和各策略子图共同使用的状态编排内核。

Agent Harness 是本项目对运行治理能力的统称，不定义特殊的 Harness 图类型。`ResearchMode`、`ResearchStrategyGraph` 和 `StrategyRegistry` 是项目内契约；顶层运行图与各策略子图都由 LangGraph `StateGraph` 构建。LangGraph 官方提供的是 `StateGraph`、State、Runtime、Node、Edge、Subgraph 和 Checkpointer 等基础能力。

## 5. 总体架构

系统采用顶层运行图加研究策略子图的结构，Harness 治理能力贯穿这些图：

```text
API / CLI / Worker
        ↓
ResearchApplicationService
        ↓
Top-level runtime graph (`StateGraph`)
  ├── load_session
  ├── initialize_turn
  ├── manage_short_term_context
  ├── classify_intent
  ├── recall_memory
  ├── decide_action
  │     ├── existing_evidence
  │     └── ResearchMode
  │           ├── WorkflowResearchGraph
  │           ├── PlanExecuteResearchGraph
  │           └── MultiAgentResearchGraph
  ├── select_response_mode
  │     ├── AnswerGraph
  │     ├── BriefGraph
  │     └── ReportGraph
  ├── dispatch_memory_consolidation
  ├── finalize_turn
  └── persist_session
```

Application 层只调用编译后的顶层运行图。研究策略、Response 和 Memory Graph 通过注册机制成为其子图，Agent Harness 则由这些图与 Runtime Context、Tool Gateway、Checkpoint、Memory 和观测策略共同构成。

## 6. 模块边界

推荐目录结构如下：

```text
src/deeptrace/
├── domain/
│   ├── conversation.py
│   ├── evidence.py
│   ├── memory.py
│   ├── execution.py
│   └── result.py
├── harness/
│   ├── graph.py
│   ├── state.py
│   ├── context.py
│   ├── registry.py
│   ├── contracts.py
│   ├── policies/
│   │   ├── intent.py
│   │   ├── routing.py
│   │   ├── budget.py
│   │   ├── freshness.py
│   │   └── response.py
│   ├── middleware/
│   │   ├── model.py
│   │   ├── tools.py
│   │   ├── context.py
│   │   └── telemetry.py
│   └── memory/
│       ├── graph.py
│       ├── recall.py
│       ├── write.py
│       ├── consolidate.py
│       └── forget.py
├── strategies/
│   ├── workflow/
│   ├── plan_execute/
│   └── multi_agent/
├── responses/
│   ├── answer.py
│   ├── brief.py
│   ├── report.py
│   └── citations.py
├── capabilities/
│   ├── search.py
│   ├── fetch.py
│   ├── retrieve.py
│   └── tools.py
├── application/
│   ├── service.py
│   └── registry.py
├── infrastructure/
│   ├── llm/
│   ├── persistence/
│   ├── checkpoint/
│   ├── memory_store/
│   ├── queue/
│   └── web/
└── interfaces/
    ├── api.py
    ├── cli.py
    └── worker.py
```

依赖规则如下：

- Domain 不依赖 LangGraph、数据库和模型 SDK。
- Strategy 不创建模型、数据库、Fetcher 或 Embedding 实例。
- Graph 节点通过 `Runtime[HarnessContext]` 获取运行依赖。
- Infrastructure 实现接口，但不决定研究流程。
- API 和 Worker 不依赖具体研究策略子图的节点或状态。
- 子图仅通过可序列化输入输出契约交换数据。
- 大型网页正文和向量不进入 Graph State，只保存引用 ID。

## 7. Harness State

Harness 状态分成会话级状态与单轮状态：

```python
class HarnessState(TypedDict):
    conversation: ConversationState
    turn: TurnState
```

`thread_id` 标识一段持续会话，`run_id` 标识会话中的一次用户请求。同一个 thread 可以包含多个 run。

### 7.1 ConversationState

会话级状态通过 Checkpointer 跨多轮保存：

```python
class ConversationState(TypedDict):
    thread_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    summary: ConversationSummary
    active_mode: Literal["workflow", "plan_execute", "multi_agent"]
    user_memory_refs: list[str]
    workspace_memory_refs: list[str]
    evidence_ids: list[str]
    established_findings: list[Finding]
    unresolved_gaps: list[str]
    created_at: str
    updated_at: str
    state_version: int
```

### 7.2 TurnState

每次调用开始时，`initialize_turn` 完整重置单轮状态，避免继承上一轮临时字段：

```python
class TurnState(TypedDict):
    run_id: str
    user_input: str
    intent: ConversationIntent
    selected_mode: Literal["workflow", "plan_execute", "multi_agent"]
    response_mode: Literal["answer", "brief", "report"]
    requires_research: bool
    research_request: ResearchRequest | None
    research_outcome: ResearchOutcome | None
    recalled_memory_ids: list[str]
    active_evidence_ids: list[str]
    budget: BudgetSnapshot
    status: ExecutionStatus
    error: ErrorRecord | None
```

### 7.3 Runtime Context

不可序列化依赖通过 LangGraph Runtime Context 注入：

```python
@dataclass(frozen=True)
class HarnessContext:
    user_id: str
    workspace_id: str
    model_gateway: ModelGateway
    tool_gateway: ToolGateway
    evidence_store: EvidenceStore
    event_sink: EventSink
    clock: Clock
```

数据库连接、模型客户端、Fetcher、Embedding 模型、锁和 Singleflight Future 不进入 Graph State。

## 8. 子图契约与状态隔离

所有研究策略子图接受统一输入并返回统一结果：

```python
class ResearchInput(BaseModel):
    run_id: str
    thread_id: str
    question: str
    conversation_summary: ConversationSummary
    prior_evidence_ids: list[str]
    unresolved_gaps: list[str]
    budget: BudgetSnapshot
    current_date: str
    timezone: str

class ResearchOutcome(BaseModel):
    mode: str
    evidence_ids: list[str]
    findings: list[Finding]
    unresolved_gaps: list[str]
    executed_steps: int
    termination_reason: str
```

每个研究策略子图保留私有 State。Harness 不感知查询队列、计划任务、Researcher 消息和 Supervisor 轮次等内部字段。子图结束后仅将 `ResearchOutcome` 合并回主图。

## 9. 三种研究模式与策略子图

### 9.1 Workflow

Workflow 是固定代码路径，不称为自主 Agent：

```text
START → plan_queries → parallel_research → evaluate → END
```

模型生成查询，Graph 确定性执行并行搜索和抓取。Evaluation 只判断资料是否可用于回答，不进入动态重规划。

### 9.2 Plan-and-Execute

Plan-and-Execute 使用显式 LangGraph 循环替代现有 Python `while`：

```text
START → plan → select_task → execute_tools → evaluate
                   ↑                            ↓
                   └──────── replan ←──────────┤
                                               └── END
```

计划、活动任务、完成任务、工具消息、评估结果和重规划次数全部进入可持久化 State。结构化 Decision 与条件边控制完成、阻塞和重规划。

### 9.3 Multi-Agent

Multi-Agent 使用 Supervisor 和 Researcher 子图：

```text
START → supervisor_plan
      → Send(ResearcherGraph × N)
      → aggregate
      → supervisor_evaluate
      → follow_up 或 END
```

Supervisor 只负责拆解、委派和完成判断，不直接访问网络。每个 Researcher 拥有隔离的消息、任务视图和本地额度。Researcher 通过 `Send` 并发执行，一个任务失败不取消同批其他任务。

## 10. 多轮会话与意图路由

支持以下意图：

- `conversation`
- `clarification`
- `research`
- `incremental_research`
- `switch_mode`
- `report_request`
- `memory_update`

普通追问优先使用短期状态和已有 Evidence，不启动新研究。增量研究继承 ConversationSummary、有效 Evidence 和未解决缺口。研究模式切换不会清空会话，但旧证据必须重新经过时效性与适用范围检查。

## 11. 响应模式

研究深度和输出形式是两个独立选择：

| 标识 | 行为 |
| --- | --- |
| `answer` | 默认，自然简洁地回答并附少量引用 |
| `brief` | 输出结构化摘要、对比或阶段性结论 |
| `report` | 仅在用户明确要求报告时生成正式报告 |

`AnswerGraph` 和 `BriefGraph` 默认不联网，只使用本轮已有 Evidence。`ReportGraph` 先检查证据是否覆盖用户请求范围；若用户增加了新范围，则先运行当前研究策略子图，再生成报告。

三种输出共享 `CitationFormatter` 和 Evidence 校验，不允许引用没有实际进入输出上下文的来源。

## 12. 短期记忆与动态压缩

短期记忆属于 thread-scoped Graph State，由 Checkpointer 保存。它包含最近消息、结构化摘要、当前研究主题、用户约束、已确认结论、未解决问题和 Evidence 引用。

Context Middleware 按 Token 预算工作：

```text
低于软阈值
  → 保留当前消息窗口
达到软阈值
  → 压缩较早消息并保留最近 N 轮原文
达到硬阈值
  → 移除大型工具观察，只保留 Evidence ID
```

压缩结果使用结构化模型，而不是单段自由文本：

```python
class ConversationSummary(BaseModel):
    topic: str
    user_constraints: list[str]
    established_facts: list[str]
    referenced_entities: dict[str, str]
    unresolved_questions: list[str]
    previous_conclusions: list[str]
```

动态压缩必须保留用户约束、实体指代、Evidence ID 和未解决问题，并确保多次压缩后摘要大小有上限。

## 13. 长期记忆生命周期

长期记忆使用 LangGraph Store 跨 thread 保存，采用 user、workspace、thread 和 global 四级作用域。其中 thread 主要由 Checkpoint 管理，Store 只在需要跨会话访问时保存引用或沉淀结果。

### 13.1 记忆类型

- Preference：稳定用户偏好。
- Fact：经过来源支持的结构化事实。
- Evidence：原始网页正文及其元数据。
- Episode：可复用的研究执行经验。

系统 Prompt、工具规则和研究规范作为版本化代码或配置维护，不允许 Agent 自动改写。

### 13.2 何时存

- 用户明确要求记住某项偏好。
- 可靠网页抓取、质量校验和去重完成。
- 研究结束后从有引用支持的结果中沉淀事实。
- 稳定偏好被重复确认并通过写入策略。

临时表达、失败调用、无来源结论、敏感凭据和一次性中间推理不写入长期记忆。

### 13.3 存什么

统一记录模型包含：类型、namespace、结构化内容、来源引用、置信度、时效状态、创建与更新时间、到期时间、版本、替代关系和生命周期状态。Evidence 另外保存规范化 URL、正文 Hash、抓取时间、发布时间和来源质量。

### 13.4 如何组织

命名空间至少包含作用域与所有者：

```text
(user, user_id, preferences)
(workspace, workspace_id, evidence)
(workspace, workspace_id, facts)
(global, episodes, mode, version)
```

默认禁止跨 user 或 workspace 召回。Global 只接收经过显式策略筛选、不含私人数据的研究经验。

### 13.5 何时召回

采用自动触发为主、Agent 工具为辅的双通道：

- Harness 在新会话、增量研究、报告生成和证据缺口场景自动召回。
- 同一会话的普通追问优先使用短期记忆，通常不访问长期 Store。
- Agent 在执行中可调用 `search_memory` 处理具体缺口。
- 强时效问题可召回历史记录作为导航线索，但必须刷新过期事实。

召回排序综合语义相似度、时效、置信度、来源质量和作用域匹配，不单独依赖向量相似度。

### 13.6 如何更新

事实和 Evidence 采用版本化更新。新版本通过 `supersedes` 关联旧版本，用户纠正、重新抓取和置信度变化均保留审计轨迹。Preference 可以更新当前值，但同样保留变更历史。

### 13.7 如何遗忘

记忆状态依次为 candidate、active、stale、superseded、expired 或 deleted。遗忘分为：

1. 检索遗忘：降权或不进入召回结果。
2. 逻辑删除：标记 deleted 并保留审计记录。
3. 物理删除：根据用户请求或数据保留策略彻底清除。

系统通过 TTL、时效衰减、来源失效、冲突替代、用户删除和定期清理触发遗忘。

## 14. Tool Harness

### 14.1 原子工具

第一版研究工具为：

- `search_web`
- `fetch_page`
- `search_memory`

现有 `research_topic` 改成 `ResearchTopicGraph`，由查询生成、搜索、URL 选择、并行抓取和 Evidence 入库组成。组合行为使用子图，外部环境能力使用 Tool。

`finish_task` 和 `finish_research` 不再作为工具。它们改成结构化 `AgentDecision`，由 `Command` 或条件边决定完成、重规划和阻塞路径。

### 14.2 工具执行管道

所有调用依次经过：

```text
Registry Resolution
→ Mode Allowlist
→ Arguments Validation
→ Security Policy
→ Idempotency Check
→ Budget Reservation
→ Cache / Singleflight
→ Start Event
→ Timeout / Retry
→ Result Normalization
→ Evidence Ingestion
→ Budget Commit
→ Completion Event
```

ToolResult 只向模型返回受控预览和 `data_ref`，大型正文保存在 Evidence Store。

### 14.3 权限

- Workflow 由 Graph 节点确定性调用工具。
- Plan-and-Execute 的 Executor 可以选择允许的研究工具。
- Multi-Agent 的 Researcher 可以使用研究工具，Supervisor 不可联网。
- Answer、Brief 和 Report 默认只读取已有 Evidence。
- Memory Consolidation 只能访问 Memory Store。

### 14.4 额度

BudgetManager 支持 Run、Mode 和 Agent 三级额度，覆盖模型调用、工具调用、网络请求、抓取页数、Token、执行轮次和墙钟截止时间。

并发请求使用预留、提交和释放机制，避免多个 Researcher 同时读取剩余额度导致超限。缓存命中与失败尝试分别记录，预算策略明确决定是否计费。

### 14.5 缓存与 Singleflight

Search Cache 使用规范化查询、Provider 和选项作为键。Page Cache 使用规范化 URL 和内容版本作为键。相同查询或 URL 的并发请求共享一个运行中 Future，只有实际请求方消耗网络额度。

### 14.6 重试与幂等性

参数、权限和内容质量错误不自动重试。连接错误、HTTP 429 和部分 5xx 根据有限退避策略重试。Provider 临时错误使用 LangGraph Node RetryPolicy。结构化输出最多进入一次修复节点。

工具调用的幂等键由 run、节点、任务、工具名和规范化参数组成。Checkpoint 恢复后优先读取 Tool Execution Ledger，避免重复调用和重复写入。

## 15. 持久化与分布式运行

MySQL 作为权威数据库，Redis 保留。职责如下：

### 15.1 MySQL

- Conversation 与 Research Run。
- 有序 Event。
- Tool Execution Ledger。
- 通过社区 `langgraph-checkpoint-mysql[asyncmy]` 保存项目使用的 LangGraph Checkpoint 能力。
- 项目自建的 Long-term Memory Store 与 Repository。
- Evidence 元数据。

### 15.2 Evidence Store

Evidence Store 是正文的唯一所有者。Local 使用文件实现，Distributed 使用 MySQL 保存规范化、分块且有大小上限的正文记录。Graph State 和长期记忆只保存 Evidence 引用。

### 15.3 Redis

- Job Stream。
- Worker Wakeup。
- Cancel Signal。
- 必要的短期分布式协调。

Redis 不保存权威运行结果。Redis 状态丢失后，可根据 MySQL 中未完成的 Run 重新投递。

### 15.4 Local 与 Distributed 配置

两个 Deployment Runtime 使用相同的 Harness、Graph 和存储协议，但采用不同 Adapter：

| 能力 | Local | Distributed |
| --- | --- | --- |
| Graph Checkpoint | `AsyncSqliteSaver` | 社区 `langgraph-checkpoint-mysql[asyncmy]` 提供的异步 MySQL Saver |
| Long-term Store | 开发用进程内 Store；重启后不承诺保留 | 项目自建 MySQL Memory Store 与 Repository |
| Run 记录 | SQLite 或现有文件 Adapter | MySQL Repository |
| Evidence 正文 | 本地文件 | MySQL Evidence Store |
| 任务执行 | API 进程内异步任务 | Redis Stream 与独立 Worker |

Local 的目标是零外部服务依赖的开发与测试，不宣称跨进程长期记忆和生产级恢复。需要验证完整长期记忆、Worker 接管和节点级持久化恢复时，必须使用 Distributed 配置。两种配置不得通过条件分支改变研究模式的业务语义。

## 16. Checkpoint、恢复与幂等

执行身份包括 `thread_id`、`run_id`、`checkpoint_id`、`attempt_id` 和 `tool_call_id`。

Worker 获取数据库 Lease 后使用 `thread_id` 调用编译后的顶层运行图。Graph 在节点边界保存 Checkpoint。Worker 崩溃后 Lease 过期，Recovery Scanner 重新投递任务，新 Worker 从最近 Checkpoint 恢复。

系统语义定义为：

```text
At-least-once delivery
+ checkpointed execution
+ idempotent side effects
```

纯计算节点允许重放。模型节点成功后保存结果，恢复时复用已完成结果。工具和 Memory 写入先检查 Tool Execution Ledger 或幂等写入记录。

## 17. Human-in-the-loop 与取消

第一版仅在以下场景使用 LangGraph `interrupt`：

- 任务需要突破已配置预算。
- 长期记忆存在无法自动解决的冲突。
- 用户请求删除跨会话或跨项目数据。
- 后续增加的工具包含高风险外部写操作。
- 意图歧义会显著改变任务范围。

取消请求先持久化到 MySQL，再通过 Redis 通知 Worker。取消状态在节点和 Tool Gateway 边界检查，并传播到活动子图。已发出的远程模型请求可能无法撤回，该限制必须在文档中明确说明。

## 18. 错误处理

统一错误类别包括 transient、validation、policy、agent_recoverable、partial、fatal 和 cancelled。

- 临时连接错误有限重试。
- 参数错误返回 Agent 修正，不扣外部调用额度。
- 结构化输出失败最多修复一次。
- 证据不足进入评估和补查。
- 单个 Researcher 失败只影响自身任务。
- Writer 失败时返回已有可验证资料，不伪造完整报告。
- Checkpoint 或权威存储失败时停止运行，避免状态分叉。
- 用户取消不重试。

重试只在一个明确层级发生，禁止 Provider、Tool Gateway 和 Graph Node 对同一错误叠加重试。

终态包括 completed、partial、failed 和 cancelled。非终态包括 pending、running、cancel_requested 和 interrupted。结束原因通过结构化 `termination_reason` 单独表达。

## 19. 可观测性

系统同时输出：

- Event：面向用户界面和 SSE。
- Trace：面向开发者的 Graph、模型和工具调用链。
- Metric：面向监控与评测的聚合数据。
- Log：面向故障排查的结构化日志。

每条观测数据携带 thread、run、attempt、checkpoint、mode、graph、node、agent、task 和 tool call 等适用标识。

核心指标包括运行耗时、首响应时间、节点次数、模型 Token、工具次数、缓存命中、失败、Checkpoint 恢复、Memory 召回采用率、压缩率、过期拦截率、Researcher 并发度和重复搜索率。

核心 Harness 不依赖 LangSmith 才能运行。开发环境可选接入 LangSmith；基础 Trace 使用供应商中立的结构化接口，并为 OpenTelemetry Adapter 留出边界。

## 20. 测试与评测

### 20.1 单元测试

覆盖 Memory 生命周期、TTL、Evidence 去重、引用、Budget、研究模式注册、错误分类和纯路由策略。

### 20.2 Graph 路由测试

使用脚本化模型和内存 Checkpointer 验证：普通追问不进入研究、增量研究进入所选研究模式、报告意图进入 Report、Plan-and-Execute 可以重规划、Multi-Agent 使用 `Send` 并发派发。

### 20.3 Tool Harness 测试

覆盖权限、参数、配额并发、Singleflight、重试幂等、URL 安全、大型结果卸载和 Evidence 入库。

### 20.4 恢复测试

分别在 Planner 后、搜索后、部分 Researcher 完成后、Writer 前、Memory 写入后和 Interrupt 期间模拟 Worker 崩溃，验证恢复后不重复已完成副作用。

### 20.5 Memory 评测

对何时存、存什么、如何组织、何时召回、如何更新和如何遗忘分别建立测试。动态压缩需验证用户约束、实体指代、Evidence ID 和未解决问题不丢失，且多次压缩后摘要大小受控。

### 20.6 研究模式对照评测

使用同一研究问题集比较 Workflow、Plan-and-Execute 和 Multi-Agent 的 Evidence 覆盖、引用有效性、未解决缺口、延迟、Token、网络次数、重复来源和回答质量。Auto Mode 只在该评测形成稳定基线后设计。

## 21. 实施顺序

1. 固化当前外部行为和评测基线。
2. 建立 Domain Contracts。
3. 引入 MySQL Checkpointer、Memory Store、Evidence Store 与 Repository。
4. 建立顶层运行图和多轮会话入口。
5. 建立 Tool Gateway、Evidence Store 和幂等 Ledger。
6. 实现 WorkflowResearchGraph。
7. 实现 PlanExecuteResearchGraph 并删除手写循环。
8. 实现 MultiAgentResearchGraph 与 Researcher 子图。
9. 实现 Answer、Brief 和 Report Graph。
10. 实现短期记忆压缩与长期记忆生命周期。
11. 接入 Worker 节点级恢复、取消和 Interrupt。
12. 完善评测、架构文档、运行手册和面试材料。
13. 基于三种研究模式的评测结果另行设计 Auto Mode。

## 22. 验收标准

重构完成必须满足：

1. 三种研究模式全部通过同一个顶层运行图执行。
2. 不再存在手写 Agent 编排循环。
3. 每种研究策略都是可独立测试的 LangGraph 子图。
4. 同一 thread 支持连续追问、增量研究和模式切换。
5. 默认返回简洁回答，仅在明确请求时生成报告。
6. 短期记忆支持滑动窗口和结构化动态压缩。
7. 长期记忆覆盖完整六阶段生命周期和四级作用域。
8. 工具通过统一中间件执行并形成可追溯 Evidence。
9. Graph 可以从持久化 Checkpoint 恢复。
10. 恢复后不重复已完成的工具副作用。
11. API、Worker 和 UI 不依赖具体研究策略子图实现。
12. 所有引用都可追溯到实际 Evidence。
13. 三种研究模式有可重复的质量、成本和延迟对照评测。

## 23. 简历与面试表述边界

推荐表述为：

> 基于 LangGraph 重构模块化 Research Agent Harness，通过主图与可插拔子图统一 Workflow、Plan-and-Execute 和 Multi-Agent 三类研究策略；实现多轮会话、动态上下文压缩、长期记忆生命周期、工具中间件、节点级 Checkpoint 恢复、分层预算、证据追踪及分布式 Worker，并建立质量、成本与延迟对照评测体系。

在对应功能实际完成并通过验证前，不应把设计中的能力写成已经交付的项目成果。不宣称符合不存在的统一 Harness 行业标准，也不宣称 Exactly-once、生产级高可用或未经过压测验证的性能指标。
