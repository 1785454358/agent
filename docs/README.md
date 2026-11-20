# DeepResearch 文档

这里提供项目使用、架构设计、部署和真实研究案例的阅读入口。

## 使用与展示

- [自动模式路由与三策略同题实测](benchmarks/2026-11-18-mode-routing/README.md)：默认自动选择、三个独立策略的真实回答对照、路由规则修复和复杂任务的部分完成边界。

- [真实新对话验收与录屏](benchmarks/2026-11-18-new-conversation/README.md)：浏览器实测、阶段事件修复、录屏复现命令与保留的回答质量问题。

- [项目首页](../README.md)：使用场景、快速体验、技术亮点与源码入口。
- [Docker 打包与运行](deployment/docker.md)：镜像构建、单机运行、分布式 Compose 和镜像验收。
- [真实研究案例](showcase/case-asyncio.md)：Python 官方文档研究的原始回答、配置、来源与完整指标。
- [设计参考与演进方向](showcase/mature-projects.md)：同类成熟项目的展示和工程实践。
- [工作台截图](assets/deepresearch-workbench.png)：使用固定示例数据的交互演示界面，可通过首页的快速体验启动。

## 架构与源码

- [按证据变化推进的研究流程规范](superpowers/specs/2026-11-19-incremental-research-flow-design.md)：同类项目调研、任务契约、增量核验、冲突重验、缺口恢复和交付终审。
- [增量研究流程实现与实测](benchmarks/2026-11-19-incremental-research-flow/README.md)：三种策略的 full/delta/reused 轨迹、真实模型 token、必要回退和保留的质量缺口。
- [回答质量优化实现与验收](benchmarks/2026-11-19-answer-quality-implementation/README.md)：章节与 API 定位、补读、事实/设计契约、可追溯终审，以及未通过的真实质量样本。

- [论文深度研究链路修复与实测](benchmarks/2026-11-17-scholarly-research/README.md)：真实论文比较题的全文获取、PDF、需求阅读、来源状态与独立核查预算修复，以及保留的失败样本与能力边界。

- [Agent 评测与回归验收](benchmarks/2026-11-07-evaluation/README.md)：跨版本/策略的受控配对比较、评分溯源、显式门禁、可复现报告与简历表述。
- [真实 Agent 策略评测](benchmarks/2026-11-07-real-evaluation/README.md)：12 道冻结资料题 × 四种配置的真实模型执行、两道联网补测、独立评分、校准失败与实际能力边界。
- [真实失败审查与优化回归](benchmarks/2026-11-07-answer-optimization/README.md)：Agent 审查、协议与评分切句修复、提示词候选的失败门禁及撤回、原始答案与离线复现输入。
- [成熟 Harness 调研与真实对照](benchmarks/2026-11-08-harness-scope-review/README.md)：Deep Agents 等官方方案调研、两轮契约/审查实验、44 次真实执行、退化归因与默认策略保留。
- [回答组件回放与引用恢复](benchmarks/2026-11-08-answer-review-boundary/README.md)：60 次真实组件生成、独立评分与失败候选撤回、共享预算内的引用协议恢复，以及确认的原文摘录遗漏。
- [Agent Harness 架构](architecture/agent-harness.md)：Session Graph、默认批量路径、可选工具循环、Gateway、预算和恢复机制。
- [LangSmith Tracing 与评测](architecture/langsmith.md)：原生调用树、30 道参考题、指标定义与简历表述；[迁移验证与云端实验](benchmarks/2026-11-09-langsmith/README.md)。旧自建评测报告仅作历史记录，其中旧命令已退役。
- [核心 Runtime 全量验收](benchmarks/2026-11-09-full-acceptance/README.md)：两轮 180 次真实执行、逐题门禁、Trace 驱动修复、联网补测及未解决问题；[验收规则与命令](architecture/acceptance.md)。
- [失败根因定位与优化](benchmarks/2026-11-09-root-cause-optimization/README.md)：规划范围偏移、原文条件截断、审查协议及版本搜索修复，含重复执行的改善与残留失败。
- [读取覆盖修复与重复验收](benchmarks/2026-11-09-query-coverage/README.md)：标识符独占窗口、完整提示块和 API 边界修复；40 次真实运行与调用次数观察。
- [Harness 运行时优化与验收](architecture/2026-10-10-harness-runtime-implementation.md)：独立任务复用、持久预算、实际用量及验证边界。
- [DeepSeek 真实 API 重测](architecture/2026-10-10-deepseek-live-retest.md)：新模型的真实研究、工具循环、usage／恢复核对与失败定位。
- [研究完成与取材优化](architecture/2026-10-11-research-completion.md)：Workflow 完成语义、有限补查、来源约束和后续真实 API 验证。
- [未完成根因与边界修复](architecture/2026-10-11-research-boundaries.md)：分支约束丢失、引用协议、核验误拒绝及最新真实 API 重测。
- [回答质量优化与实测](architecture/2026-10-23-answer-quality.md)：固定题对照、自适应篇幅、Markdown 展示、材料窗口与思考模式实验。
- [引用审查与逐句评分修复](architecture/2026-10-24-citation-quality.md)：简答与报告审查接入、实际可见原文、重复误引反例和真实追问验证。
- [成熟产品同题实测](benchmarks/2026-10-24-product-comparison/comparison.md)：ChatGPT、Perplexity、Gemini 匿名模式与本项目的真实输出、关键差距和原始记录。
- [取材与有限补查优化实测](benchmarks/2026-10-24-research-recovery/results.md)：开放发现、v3 原文交付、完整正文与单轮补查的实现、前后原始答案及仍未解决的问题。
- [Harness 回答质量断点与读取修复](benchmarks/2026-10-25-reading-fidelity/results.md)：列表/代码保留、跨语言读取、条件组与焦点窗口、预算内连接恢复，以及无效审查实验和真实失败样本。
- [缺口驱动的原文回读](benchmarks/2026-10-25-gap-reread/results.md)：先回读再搜索、实际短引用的完整性校验、固定失败样本重放及两道联网题的真实输出与剩余缺口。
- [记忆模块](architecture/memory.md)：记忆生命周期、版本更新、召回、证据准入与存储设计。
- [后端使用说明](../backend/README.md)：环境变量、API、本地与分布式运行方式。

建议先体验工作台，再阅读真实案例，最后结合架构文档和源码了解实现。测试与构建命令见[项目首页](../README.md#测试与工程验证)。
