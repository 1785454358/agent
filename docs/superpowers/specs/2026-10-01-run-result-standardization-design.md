# Harness 简化：统一应用运行结果

日期：2026-10-01。状态：用户已于本轮确认开始实施，并允许真实 API 测试。

## 目标与范围

应用层不再只返回 ResponseOutcome，而是返回一份轻量 ApplicationRunResult。保留 Harness 的最终状态、研究停止原因、执行步数、未解决问题、回答和来源。Local / Worker 不再根据回答是否可用重新判断整个研究是否完成。

这轮只实施上轮建议的第 1 项。预算恢复失败策略、历史证据上限、真实 Token / 成本计量和评测扩容分别处理，不混入此改动。用户现有引用、评测、配置和其他文档修改保持原样；不修改数据库 schema、依赖或配置文件。

## 已核实的问题

- Harness._finalize_turn 同时检查 ResearchOutcome 和 ResponseOutcome，研究达到 max_iterations 时可正确标记 PARTIAL。
- ResearchApplicationService._extract_outcome 丢弃 turn.status 和 ResearchOutcome，仅返回 ResponseOutcome。
- Local / Worker 随后根据 response.partial_reason 重新生成状态。最小复现中，Harness 为 partial，Worker 变为 completed；max_iterations 变为 completed；7 个 executed_steps 变成固定 1；unresolved_gaps 丢失。
- Worker 当前的 TokenUsage、stage_seconds 等仍是未接通的占位数据。这轮不把执行步数当作真实模型用量，不宣称已解决成本计量。
- 两个运行适配器重复核验引用来源、提取 URL、生成完成状态与结束事件。

## 方案比较

### 推荐：应用层返回统一轻量结果

新增一个 ApplicationRunResult 数据契约，保留原始 ResponseOutcome 和可选 ResearchOutcome，附带最终状态、来源 URL 及执行摘要。应用服务完成一次结果提取和引用来源投影；两端只映射到现有公开运行记录。会显式迁移调用者，但无需兼容代理、插件注册器或新的运行时。

### 不采用：在 Local / Worker 各补一次状态回查

可以少改 service.invoke 的返回类型，但两端都依赖 graph.aget_state，再次重复解释状态；无 checkpointer 的调用还需要额外分支。问题会从一次结果丢失变成两份恢复逻辑。

### 不采用：直接返回整个 HarnessState，或立即使用 AgentResult 替代

完整 State 暴露消息、会话及 checkpoint 内部结构，适配器更耦合。AgentResult 包含尚未采集的 Token / 成本等展示字段，将它作为应用层真实执行契约会掩盖未知数据。本轮保留 AgentResult 作为 Worker 的既有适配输出，不把它扩展成万能结果。

## 返回契约

在 application/result.py 定义 Pydantic ApplicationRunResult，extra=forbid；字段如下。

| 字段 | 来源与语义 |
| --- | --- |
| run_id / thread_id | 已校验的 ApplicationResearchRequest 身份 |
| status | Harness 终态 completed / partial，直接保留；非终态拒绝作为成功返回 |
| response_outcome | 当前 turn 的 ResponseOutcome，保留内容、引用及 response.partial_reason |
| research_outcome | 当前 turn 的 ResearchOutcome，直接回答 / 控制意图允许 None |
| termination_reason | 研究非 completed 的原因优先；否则用 response.partial_reason；正常 completed 返回 completed；partial 且没有原因时返回 partial |
| executed_steps | research.executed_steps；没有本轮研究时为 0，不伪装成模型调用数 |
| unresolved_gaps | 本轮 research.unresolved_gaps 的独立列表；没有研究时为空 |
| sources | 按 response.cited_evidence_ids 顺序在当前 workspace 核验并投影出的 canonical_url 列表 |

不复制 ResponseOutcome 的 content / citations 等为另一套字段，不新增旧字段转发属性，也不以 hasattr / getattr 兼容旧返回类型。所有生产调用者和相关测试显式迁移到 result.response_outcome。

最终状态不因 response.partial_reason 为空而升级。切换模式、显式记忆保存等既有控制响应仍遵循当前 Harness 状态和 reason，不在此次重新定义这些意图的成功语义。

异常、取消、身份不匹配仍走现有异常通道，Local / Worker 继续处理自己的 failed / cancelled / lease_lost 生命周期；不把异常转换成伪造的正常结果。

## 结果提取与适配

1. service.invoke 的 fresh / continuation / resume 路径均调用同一个结果提取边界，返回 ApplicationRunResult。
2. 缺失 ResponseOutcome 保留原来明确失败的行为；缺失或非 completed / partial 的 turn.status 作为契约错误，不从其他字段猜测。
3. 结果提取统一解析 research / response，生成 termination_reason、executed_steps、unresolved_gaps。
4. 有引用才使用现有 EvidenceStore.get_many 核验当前 workspace 来源。无引用不发查询；来源读取失败仍让本次适配失败，保持原运行边界，不把缺失来源静默包装成成功。只投影元数据，不读取正文。
5. Local 将回答、status、termination_reason、sources、unresolved_gaps 写入现有 RunRecord，事件文案区分 completed / partial；不凭空生成 Token usage。
6. Worker 映射相同字段到既有 AgentResult，steps 不再固定为 1；未接通的 provider_usage / role_usage / stage_seconds 保持现有兼容形态，文档明确不代表真实测量。
7. CLI 的“模型调用步数”文案调整为“执行步数”，避免混淆 ResearchOutcome.executed_steps 和 Provider 调用数。

不新建 Result Service、状态机或映射注册器。SQL repository 已支持 steps 与 unresolved_gaps，无需 schema 改动。

## 迁移边界

生产文件：application/result.py、application/research.py、application/agent_adapter.py、runtime/local.py，以及 CLI 文案。

相关测试迁移：application 服务、Local、Worker/Harness 适配、Harness 响应切片、三模式集成、恢复与真实 smoke 中消费 service.invoke 返回值的位置。响应子图本身仍返回 ResponseOutcome，不修改它的返回契约，也不触碰用户正在修改的 responses/citations.py 与对应测试。

用户未提交的 eval/runner.py 目前忽略 service.invoke 的返回值、从 snapshot 取数据，本轮无需修改。不要为统一结果顺带迁移这套评测或覆盖它的真实测试。

## 验收

### 离线回归

先写能捕获状态丢失的回归，观察 RED，再实现：

- 研究 max_iterations、回答引用有效：应用、Local、Worker 均为 partial，保留研究退出原因、7 步与未解决问题。
- 研究 completed、回答失败：保留 response.partial_reason 和整体 partial，不错误称研究完整成功。
- 研究与回答均成功：三层状态均 completed，来源 URL 顺序与引用一致。
- 直接回答没有本轮 ResearchOutcome：executed_steps=0，不借用历史研究统计；控制意图 reason 保留。
- 缺失响应、非终态、来源缺失 / 跨 workspace、身份不匹配仍明确失败。
- continuation / resume 返回同一结果契约，不重复研究，不改变 tool ledger / checkpoint 行为。
- 真实 Memory / Evidence Store、SQLite repository 等可用真实组件优先使用；模型 / 搜索外部边界可脚本化。

完成专项、全仓库 pytest -m "not real"、修改源文件 Ruff、测试 I/F、格式与 git diff --check。不得仅通过修改测试的预期来消除 partial → completed 的问题。

### 真实 API 验收

本地已确认 OPENAI_API_KEY、OPENAI_BASE_URL、OPENAI_MODEL、TAVILY_API_KEY 已配置，仅检查存在性，没有输出值。用户已授权真实调用，无需再次请求 API 使用许可。

- 先做 1 题 Workflow smoke，真实模型 + Tavily + 网页抓取，问题使用公开技术主题，不提交项目源码或密钥给服务商。
- 使用临时运行目录和独立 run/thread ID，不复用现有 runs、历史记忆或向量；finally 关闭 bundle。
- 测试采用 lexical 记忆模式，明确不把这次结果宣传成 Chroma / BGE-M3 / MySQL / Redis 的真实集成验收。
- 测试环境限制每分支 Agent 最多 3 轮、每次模型输出最多 1024 token、全程超时 180 秒；测试专用包装器最多允许 12 次逻辑 ModelGateway 调用与 12 次 ToolGateway.execute 调用，超限在调用前中止。
- 逻辑调用上限不等同于网络请求数；保留现有传输重试，其尝试数可能更多。不承诺缺乏价格配置时的美元费用上限。日志不输出凭据、请求头或 .env 内容。
- 必须验证真实返回的 ApplicationRunResult 与 Harness snapshot 状态、原因、步数和 gaps 一致，来源非空且回答确有引用；单次 partial 如实记录，不仅凭有回答宣称研究完成。
- 真实服务不可用时报告错误类别与已执行范围，不重试整套评测、不无界重跑。离线回归仍可证明契约边界；没有真实调用结果就不宣称已通过真实测试。
- 首轮完成后不自动运行全模式 / 全题集 / LLM judge。若扩大真实评测规模，另行约定样本与成本预算。

## 自审

### 用户授权的预算修订（2026-10-01）

首轮 3 轮 smoke 在抓取前耗尽预算后，用户明确要求调高预算并做到端到端通过。后续单题测试改为每分支 6 轮、全局最多 32 次逻辑模型调用 / 24 次工具调用、240 秒整体超时；每调用输出仍最多 1024 token。保留独立临时数据与传输重试，不修改生产默认配置，不承诺未计量的费用上限。

后续验收增强为整体 completed、termination_reason=completed、回答无 partial_reason、有实际来源和引用，同时仍核对 Harness snapshot；不得以有引用的 partial 代替端到端完成。计划见 `../plans/2026-10-01-real-smoke-budget.md`。

6 轮测试已抓取资料但研究仍在 iteration_limit 退出，并有 evaluation_unavailable。下一次有限验证使用每分支 8 轮、输出上限 2048 token，全局仍保持 32/24 次逻辑调用与 240 秒，并记录评估器 finish_reason/schema error。不会把输出截断的假设写成已确认原因。

8 轮验证显示评估器格式正常且 sufficient=true，两个分支已完成，第三分支完成 3/4 项但尚需汇总。最后一次预算校准使用每分支 12 轮、最多 40 次模型 / 24 次工具逻辑调用、2048 输出 token、240 秒；若仍未通过，不继续累加预算，转向讨论计划维护效率。

- [x] 结果丢失已复现并定位到 service 返回边界与运行适配器。
- [x] 比较统一契约、两端回查、完整 State / AgentResult 三种方案。
- [x] 明确状态权威、原因优先级、无研究语义、异常与恢复边界。
- [x] 不扩展数据库、不增加复杂框架、不把未知成本计量描述为真实值。
- [x] 确认真实凭据存在性并界定有限调用、临时数据与资源关闭。
- [x] 用户审阅书面方案后，进入 writing-plans 与 TDD 实现。
