# Agent Harness 逐层学习文档设计

## 目标

为“多模式深度研究 Agent”建立一套可以从零学习、反复复述和用于模拟面试的架构文档。读者沿着一次请求的运行过程逐层理解 Agent Harness，不依赖背诵简历条目。

## 术语边界

- Agent Harness 是一类上层运行与治理结构。LangGraph 官方将自身定位为低层 Agent 编排运行时，并将 Deep Agents 描述为构建在 LangGraph 之上的 Agent Harness。
- `AgentHarnessGraph` 是本项目顶层 `StateGraph` 的内部类名，不是 LangGraph 官方概念。学习材料统一称为“Agent Harness 主图”，第一次出现时说明项目内部类名。
- “研究模式”面向用户与 API，领域标识为 `ResearchMode`。
- “研究策略子图”指模式对应的 LangGraph 实现，公共接口为 `ResearchStrategyGraph`。
- `StrategyRegistry` 根据 `ResearchMode` 解析策略子图。
- Workflow、Plan-and-Execute 和 Multi-Agent 是三种研究模式。
- Answer、Brief 和 Report 是响应模式，与研究模式正交。
- LangGraph 官方术语包括 `StateGraph`、State、Runtime、Node、Edge、Subgraph 和 Checkpointer。

参考资料使用 LangGraph 官方文档中的 Overview、Graph API、Context 和 Subgraphs 页面。

## 交付物

### Markdown 学习手册

路径为 `docs/architecture/agent-harness-learning-guide.md`。

它是内容的可搜索版本，包含完整文字、六张 Mermaid 图、九个理解问题、参考答案、常见误解和代码模块映射。它适合在 IDE、GitHub 和代码评审中阅读。

### HTML 逐层学习页面

路径为 `docs/architecture/agent-harness-learning.html`。

它把相同知识组织为一个逐层页面。页面使用原生 HTML、CSS、JavaScript 和 Mermaid，不依赖项目后端。Mermaid 从固定版本的 jsDelivr 资源加载。页面必须能直接打开，并在资源加载失败时显示 Mermaid 源码和明确提示。

## 学习层级

### 第零层 心智模型

先解释 Framework、Runtime、Harness 和本项目之间的关系。读者要能回答 LangGraph 提供什么，Agent Harness 又增加了什么。

### 第一层 Harness 总体架构

第一张 Mermaid 图展示 API、Agent Harness 主图、StrategyRegistry、三个研究策略子图、响应子图、Tool Gateway、Evidence Store、Memory Store、Checkpointer、MySQL 和 Redis 的关系。

### 第二层 单次请求时序

第二张 Mermaid 图使用 sequence diagram，跟踪一个已有 thread 中的增量研究请求。它必须经过请求规范化、上下文恢复、意图判断、按需长期召回、策略执行、工具调用、Evidence 入库、响应生成、记忆整理和 Checkpoint。

### 第三层 State 与 Memory 所有权

第三张 Mermaid 图区分 Conversation State、Turn State、策略子图私有 State、Runtime Context、Evidence Store 和长期 Memory Store。

本层明确工作记忆属于可恢复 State。它包含计划、任务进度、Finding、Evidence 引用、预算和未解决缺口。模型中间推理、数据库连接、锁、网页正文和客户端不进入 State。

### 第四层 三种研究策略子图

第四张 Mermaid 图在同一画布中并列展示 Workflow、Plan-and-Execute 和 Multi-Agent。每个策略都从统一 `ResearchInput` 开始，以 `ResearchOutcome` 结束。图中不得把 Writer 放进 Multi-Agent，Writer 只属于后续响应子图。

### 第五层 Tool Gateway

第五张 Mermaid 图展示 Registry、Allowlist、参数校验、安全检查、幂等账本、预算预留、Cache 与 Singleflight、执行、Evidence 入库、预算提交和事件记录的顺序。

图和文字必须说明 Provider SDK 内置重试设为零，Tool Gateway 负责超时、错误分类与幂等保护，瞬时错误由 LangGraph Node RetryPolicy 在唯一层级重放工具节点。

### 第六层 崩溃恢复

第六张 Mermaid 图使用时间线或序列图对比三个故障窗口。

1. 工具调用前崩溃，恢复后重新进入节点。
2. Provider 成功但 Ledger 未提交，恢复可能重复请求。
3. Ledger 已提交但 Checkpoint 未提交，恢复命中相同幂等键并复用结果。

本层说明 at-least-once、Lease、Provider 幂等键、Outbox 配合幂等消费者、补偿和人工确认的适用边界。

### 第七层 综合自测

收录用户确认的九个问题。

1. Harness 和 LangGraph 分别负责什么。
2. 为什么三种研究模式都需要策略子图。
3. 工作记忆为什么属于 State。
4. Evidence 正文为什么不能放进 State。
5. Tool Gateway 为什么先校验再预留预算。
6. Checkpoint 为什么不能单独解决重复调用。
7. 长期记忆为什么不能保存所有聊天。
8. Multi-Agent 为什么不允许 Supervisor 直接联网。
9. 为什么默认输出普通回答，报告需要单独触发。

每题提供回答框架、参考答案和一个继续追问。学习模式可以展开答案，面试模式隐藏答案。

## 每层页面结构

每一层按固定顺序呈现。

1. 本层问题
2. 阅读目标
3. Mermaid 图
4. 按编号逐步讲解
5. 对应项目模块
6. 常见误解
7. 自测题与答案展开

## HTML 交互

- 左侧或顶部提供八步目录，窄屏改为可换行的顶部导航。
- 页面提供上一步和下一步按钮，并显示当前层数。
- URL hash 记录当前层，刷新后仍停留在原位置。
- 本地存储记录已经访问的层和已完成的自测题。
- 学习模式允许展开参考答案。
- 面试模式隐藏所有参考答案，只保留图、问题和继续追问。
- 键盘可以正常操作导航、模式切换和答案按钮。
- 页面支持 320 像素以上宽度，不使用横向页面滚动。复杂 Mermaid 图允许在自身区域横向查看。
- 提供打印样式，打印时展开全部层级与答案。

## 内容与代码映射

学习文档以最终架构命名为准，并映射到以下模块职责。

- `backend/src/deeptrace/harness/graph.py` 对应 Agent Harness 主图。
- `backend/src/deeptrace/harness/state.py` 对应共享与单轮 State。
- `backend/src/deeptrace/harness/context.py` 对应 Runtime Context。
- `backend/src/deeptrace/harness/registry.py` 对应 StrategyRegistry。当前实现仍使用旧类名，恢复开发时统一迁移。
- `backend/src/deeptrace/tools/` 对应 Tool Gateway、策略、安全、预算和后续存储适配器。
- 三种研究策略子图在后续阶段分别替换现有 basic、deep 和 multi_agent 编排入口。

学习文档不得把尚未完成的类名写成当前已经存在的实现。最终设计与当前代码不一致时，明确标记为“最终架构对应模块”。

## 验收

- Markdown 中存在六个可解析的 Mermaid 代码块。
- HTML 中存在八个学习步骤和六张 Mermaid 图。
- 九个问题都有参考答案与继续追问。
- 学习模式和面试模式均可切换。
- 上一步、下一步、目录、URL hash、进度保存和答案展开正常工作。
- Mermaid 加载失败时页面仍能显示源码。
- 桌面和 320 像素窄屏均无正文裁切。
- 文档统一使用研究模式、研究策略子图、StrategyRegistry 和 Agent Harness 主图。
- 文档明确区分官方 LangGraph 概念与项目自定义命名。
- 简历和面试指南同步采用新术语。
- 暂停中的业务代码不在本任务中重命名或提交。
