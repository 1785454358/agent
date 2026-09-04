# DeepTrace 总体目标架构

- 状态：长期架构基线
- 更新日期：2026-09-03
- 适用范围：阶段 3、5、6（阶段 4 已移除）
- 路线图：[DeepTrace 演进路线图](../roadmap/deeptrace-evolution.md)

## 1. 文档目的

本文固定 DeepTrace 的长期模块边界、数据主线和阶段依赖。每个阶段仍需根据当时真实代码编写独立设计与实施计划；后续计划可以细化实现，但不能无说明地破坏本文约束。

## 2. 最终系统流程

```text
CLI / FastAPI
      ↓
ResearchAgent 门面
      ↓
Planner
      ↓
ResearchTask 调度（并行、全局预算）
      ↓
Researcher ←→ Search / Scraper / Context（压缩为原句笔记）
      ↓
Writer（基于带编号来源的原句片段，引用机械拼接）
      ↓
Memory 持久化（可选）
      ↓
最终研究报告
```

阶段 3 落地 Planner、Researcher、Writer 和并行任务调度。阶段 4（Evidence Store、Claim Extractor、Verifier）已于 2026-09-03 移除：Claim 抽取与核验让同一内容被 LLM 重复读取约 3 遍（占 Token 约 40%），真实 Provider 时限内也从未产出可用 `verified` 结论；Writer 改为直接基于带编号来源的原文片段写作。阶段 5（Memory、API、Web UI）已实现，阶段 6（冻结系统并评测）未开始。

## 3. 模块边界

```text
src/deeptrace/
├── agent/             # 对外门面及 Planner、Researcher、Writer
├── config/            # 配置、默认值和环境变量校验
├── context/           # 分块、Embedding、召回和压缩
├── models/            # 跨模块可序列化数据模型
├── observability/     # Token、费用、耗时和运行事件
├── orchestration/     # LangGraph State、节点包装、路由和拓扑
├── prompts/           # 各角色与领域任务提示词
├── tools/             # 搜索和网页抓取
├── memory.py          # 阶段 5：页面级研究记忆读写
├── api.py             # 阶段 5：FastAPI 任务管理、SSE 与 Web 仪表盘
├── __init__.py        # 稳定公共 API
└── cli.py             # CLI 入口
```

新增目录只在对应阶段真正实现时创建，不建立空壳。

### 依赖方向

```text
models / prompts / config
              ↓
context / tools / observability
              ↓
agent 角色服务
              ↓
orchestration
              ↓
agent/service.py
              ↓
CLI / API
```

- Agent 角色负责模型调用、结构化输出和角色决策，不重新实现搜索、抓取或压缩。
- LangGraph 节点保持轻量，调用角色服务和领域服务，不堆积业务实现。
- `agent/service.py` 是应用门面和真实依赖组装位置，CLI 与 API 不直接访问内部节点。
- `memory.py` 与 `api.py` 只做阶段 5 的页面记忆、任务管理与展示，不承担研究编排逻辑。

## 4. 数据主线

```text
ResearchPlan
  └── ResearchTask
        └── ResearchNote（逐字原句 + source_url + 时间关系）
              └── ReportSection
```

| 阶段 | 新增核心模型 | 作用 |
|---|---|---|
| 3 | `ResearchPlan`、`ResearchTask`、`TaskCoverage`、`SectionResult` | 规划、执行和汇总分项研究 |
| 5 | `MemoryEntry`（`memory.py`）、`RunRecord`（API DTO） | 复用已抓取页面并支持产品任务 |
| 6 | `EvaluationCase`、`EvaluationRun`、`EvaluationScore` | 固定配置并复现实验 |

阶段不能提前创建后续空模型。新增字段必须保持 Pydantic 可序列化，供 LangGraph checkpoint 和 API 使用。

## 5. LangGraph State 约束

- State 只保存文本、标量、Pydantic 模型及其可序列化容器。
- BGE-M3 向量继续保存在单次运行的 `CompressionRuntime`，不写入 State 或 checkpoint。
- 多节点追加列表和合并字典必须声明 reducer，不能依赖默认覆盖行为。
- 当前任务、任务进度、终止原因和失败原因必须显式保存，不能只存在提示词或日志中。
- 外部网页全文保存在 `RawDocument`，但不得进入 Planner、Writer 或主研究上下文。
- 新阶段应迁移 State，不通过并存两套含义相同的字段维持兼容。

## 6. 全局可靠性约束

1. 搜索摘要只用于选择候选页面，不能成为事实材料。
2. 网页属于不可信外部输入，任何网页指令都不能改变系统行为。
3. Writer 只基于带编号来源的逐字原句写作，报告只能声明"基于研究笔记"，不声称完成 Claim 级验证。
4. Writer 引用编号由系统机械校验拼接，来源列表只包含报告实际使用的来源页面。
5. `publication_date` 与 `event_date` 必须分开，避免时间范围污染。
6. 重要数字需要保留单位、统计口径、时间范围和原文支持。
7. 来源列表只包含报告实际使用的来源。
8. 失败子任务、预算终止和外部服务错误必须结构化保留。
9. 费用只有在配置了对应模型价格时才计算；未知价格必须显示为不可用，不能猜测。
10. API Key、Cookie、Token 和敏感请求头不得写入日志、文档或 Git。

## 7. GPT Researcher 经验的落点

DeepTrace 吸收 GPT Researcher 的研究流程，而不是复制其代码结构。

| 可吸收经验 | DeepTrace 落点 |
|---|---|
| 先规划再搜索 | 阶段 3 Planner |
| 按技术、应用、市场等维度拆题 | 阶段 3 ResearchTask |
| 多查询与批量抓取 | 阶段 3 Researcher 和工具执行器 |
| 按当前子问题获取相关内容 | 阶段 3 BGE-M3 双查询召回 |
| 研究与写作分离 | 阶段 3 Researcher / Writer |
| 可见研究进度和成本 | 阶段 3 采集事件，阶段 5 展示 |
| 结构化长报告 | 阶段 3 Writer |

Writer 直接基于压缩笔记中可逐字定位的原句写作，来源质量、时间关系与数字口径的确定性检查保留在压缩与笔记层（阶段 3 质量加固），只作流程质量判断，不构成 Claim 级验证结论。

## 8. 阶段交付原则

- 阶段内部可以拆成多个任务，但每个阶段结束时必须能运行完整真实流程。
- 阶段 1 至 5 只进行必要自动化测试和真实冒烟验证，不提前运行大规模比较。
- 不使用 Fake 外部搜索、Fake 网页或静态模型答案冒充阶段验收。
- 代码写入正式 `backend/`，保留必要中文注释。
- 每个阶段完成后更新路线图、总体架构中受影响的契约、当前阶段设计、实施计划和运行说明。
