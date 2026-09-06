# LangGraph Supervisor Plan-and-Execute Multi-Agent 设计

日期：2026-09-06

状态：用户已确认采用 LangGraph；等待书面规格复核后进入实施计划。

## 1. 目标与定位

`multi_agent` 重构为经典的分层 Agent 架构：团队层使用 Plan-and-Execute，Supervisor 负责首次规划、执行反馈评估和动态重规划；执行层并行运行多个相互隔离的 ReAct Researcher；Writer 最后只根据实际读取的网页原文生成报告。

```text
START
  → Supervisor Plan
  → Execute Ready Tasks（并行 ReAct Researchers）
  → Supervisor Replan
       ├─ 有待执行任务 → Execute Ready Tasks
       └─ 满足结束条件 → Writer
  → END
```

Basic 继续使用现有一轮 LangGraph 工作流。Deep 继续保留现有单 Agent Plan-and-Execute 实现。本轮只重构 `multi_agent` 的顶层协调，不让三个模式互相调用流程代码。

## 2. 当前问题与根因

当前 `multi_agent/agent.py` 使用手写 `for` 循环。Supervisor 每轮只返回一次临时 `dispatch/finish` 决定，没有持久研究计划，也没有明确的 pending、running、partial、completed 状态转换。协调器会无条件接受格式合法的 `finish`，即使仍有缺口、研究员名额和网络额度。

运行 `db2f3ea92e6b` 中 Supervisor 两次在 45 秒超时后降级结束，剩余补查额度没有使用。运行 `f6f6b84368bb` 中 Supervisor 虽然正常返回，却错误判断“2025 尚未发生”，在只使用 16/30 次网络额度且三个任务均为 partial 时提前结束。这两种表现分别暴露了故障降级缺失和终止条件完全交给模型的问题。

Provider 模型不会自动获得应用当前日期。现有提示只给用户问题与研究历史，因此模型可能使用过时的内置时间认知。

## 3. LangGraph 状态与节点

新增 `multi_agent/state.py`、`graph.py` 和 `nodes.py`。`agent.py` 只负责创建初始状态、调用编译后的图并把最终状态转换为 `AgentResult`。

核心状态包含：

- `question`、`current_date` 和 `timezone`；
- 持久 `tasks` 任务账本，任务记录 assignment、status、result、parent_ids；
- 当前 `ready_task_ids`、累计 Researcher 结果和下一个稳定任务 ID；
- Supervisor 循环次数、已创建 Researcher 数和确定性终止原因；
- 最终充分性、最新叶子任务缺口、Writer 上下文、来源、事件和用量统计。

图包含四个职责单一的节点：

1. `plan`：Supervisor 生成首批有限、互斥、可核对的任务并写入任务账本。
2. `execute`：选择所有依赖已满足的 pending 任务，在一个批次内通过 `asyncio.gather` 并行运行独立 ReAct Researcher，然后原子更新任务状态。
3. `replan`：Supervisor 读取压缩后的计划状态和执行反馈，保留已有任务，只添加针对叶子任务具体缺口的 follow-up，或请求结束。
4. `writer`：从所有任务实际引用的 BGE 筛选原文构造报告和最终 `AgentResult` 字段。

条件边从 `replan` 路由到 `execute` 或 `writer`。并发 Researcher 仍由 execute 节点内部的信号量和现有共享资源层管理，避免 LangGraph 动态 fan-out 与网络租约产生两套调度状态。

## 4. 计划、执行和重规划语义

首次计划默认产生不超过单批上限的任务。每个任务只覆盖一个研究方向，包含一至三个 `required_outputs`。程序分配稳定 ID，模型不能自行覆盖已有 ID。

execute 只运行 pending 且依赖已完成的任务。每个 Researcher 保持现有隔离消息、已知 URL、已读来源、本地额度、两次研究决策加一次强制收尾。单个 Researcher 失败不能取消同批任务。

replan 接收精简后的任务账本：任务 ID、目标、检查项、状态、摘要、具体缺口、来源数量和父任务；不传完整 URL 或网页原文。重规划只能：

- 保留未执行及已完成任务；
- 为 partial/blocked 叶子任务添加带 `parent_ids` 的定向补查；
- 在满足程序终止条件时结束。

重规划不允许替换整个计划，也不重新执行 completed 任务。新任务必须对应已有具体缺口，并受剩余 Researcher 数、批次大小和至少两次网络尝试的可用容量约束。

当 Supervisor 超时或连续返回无效结构时，确定性 Replanner 按 partial/blocked 叶子任务生成一轮补查任务，而不是直接结束。每个父任务最多生成一个 follow-up；其缺口被合并为不超过三个清单组。若没有可补查缺口或已无容量，则进入 Writer 并保留缺口。

## 5. 终止不变量

Supervisor 是规划者，不拥有无条件终止权。图路由器执行以下不变量：

- `sufficient=true` 且没有 pending/running 任务时可以正常结束；
- `sufficient=false`、存在 partial/blocked 叶子缺口、仍有 Researcher 名额和至少两次网络额度时，不能结束，必须进入补查；
- 达到 Supervisor 循环上限、Researcher 总数上限、网络额度不足或补查没有产生新来源时，可以以 partial 结束；
- 完全没有可用原文时为 failed；有原文但仍有关键缺口时为 partial。

最终缺口只从最新叶子任务计算。父任务已经被 follow-up 覆盖后，不再把父任务旧缺口重复带入报告；follow-up 的新缺口或未覆盖项继续保留。

该设计最多执行配置允许的有限批次，不实现无限“只要 partial 就继续”的循环。

## 6. 当前日期、失败处理与观测

每次运行在初始状态记录服务器本地的 ISO 日期和时区，并显式传给 Supervisor Plan、Replan、Researcher 与 Writer。提示明确用户指定年份相对于该日期的关系，网页内容不能覆盖日期或系统指令。

Supervisor 结构错误仍允许一次格式修复。`provider_timeout` 不进行同参数的第二次等待，立即触发确定性 Replanner，并为本轮 Supervisor 启动熔断；本次运行后续重规划使用确定性路径，避免重复 45 秒超时。

新增或保留以下关键事件：

- `planning.started/completed`；
- `researcher.queued/started/completed`；
- `replanning.started/completed/fallback`；
- `plan.finish_rejected`，说明仍有缺口和容量，拒绝提前结束；
- `research.completed`、`writing.completed`、`run.completed`。

事件只记录清洗后的原因码和可核对状态，不记录 Provider 原始异常、API Key 或隐藏推理。时间、Token 和费用继续只统计，不作为运行停止预算。

## 7. 文件边界与兼容性

主要新增或修改：

- `multi_agent/state.py`：LangGraph TypedDict、不可变 reducer 和任务账本更新；
- `multi_agent/graph.py`：`START → plan → execute → replan ↺ → writer → END`；
- `multi_agent/nodes.py`：四个图节点及确定性路由；
- `multi_agent/supervisor.py`：首次规划、重规划和确定性 fallback；
- `multi_agent/agent.py`：图调用与公共结果适配；
- `multi_agent/prompts.py`：当前日期、持久计划和 plan-patch 提示；
- 对应 `tests/multi_agent/` 状态、图、节点和回归测试。

继续复用现有 `Researcher`、`ResearcherTools`、`SharedResearchResources`、`QuotaManager` 和 Writer。API mode、CLI 参数、运行 JSON、数字标题与引用格式不变。不新增 ResearchNote、Claim、Evidence、Verifier 或逐页 LLM 摘要。

## 8. 验收场景

- 初始 r1/r2/r3 均 partial 且仍有容量时，格式合法的 insufficient finish 被拒绝并生成 r4/r5/r6。
- Supervisor 在 Replan 首次超时后不等待第二个 45 秒，确定性补查仍进入 execute。
- follow-up 完成后父任务旧缺口不再出现在最终缺口；未解决的新缺口继续保留。
- 明确传入当前日期后，不再把已经过去的目标年份判断为未来。
- pending 任务不会因某个任务 partial 或重规划而丢失，completed 任务不会重复执行。
- 并行数、总 Researcher 数、Supervisor 循环和实际网络尝试均不超过配置。
- Writer 仍只接收实际读取的原文，来源列表与上下文一致。
- Basic、Deep、API、CLI、SSE 和前端回归测试全部通过。

不运行真实付费研究作为自动化测试。真实效果在用户确认后以相同问题、模型和 30 次网络额度手动复测，并比较补查是否发生、核心覆盖、来源质量、Token 与墙钟时间。

## 9. 设计自检

- [x] 架构明确为团队层 Plan-and-Execute、执行层 Supervisor Multi-Agent、任务层 ReAct。
- [x] LangGraph 承担状态和循环路由，而非只包裹现有手写循环。
- [x] 终止条件由模型建议与程序不变量共同决定。
- [x] 超时、格式错误、提前 finish 和额度耗尽都有有限确定路径。
- [x] 任务、缺口和父子关系持久化，不会在重规划时丢失。
- [x] Basic、Deep 和事实材料路径不在重构范围。
