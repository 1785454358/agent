# DeepTrace 文档入口

## 当前状态（2026-09-03 更新）

- 阶段 1、2、3：已完成
- 阶段 4（Evidence/Claim/Verifier）：经项目所有者决策于 2026-09-03 移除。原因：Claim 抽取与核验使同一内容被 LLM 重复读取 3 遍（占 token 约 40%），且在真实 Provider 时限内从未产出 `verified` 结论；Writer 改为直接基于带编号来源的原文片段写作，引用由系统机械拼接。
- 性能优化（2026-09-03）：搜索+抓取融合（搜索轮内自动抓取 top 候选并压缩出笔记）、子任务并行（预算网关 + 有界并发）。端到端从 ~640-950s 降至 ~210-450s。
- 阶段 5（Memory 与产品化）：已实现——FastAPI 任务管理、SSE 事件流、运行持久化（runs/<id>.json）、Web 仪表盘、研究记忆（DEEPTRACE_USE_MEMORY）。
- 阶段 6（系统评测与开源对比）：未开始
- 当前代码目录：`backend/`

## 当前阅读顺序

1. [演进路线图](roadmap/deeptrace-evolution.md)
2. [总体目标架构](architecture/deeptrace-target-architecture.md)
3. [后端运行说明](../backend/README.md)

阶段 4（Evidence/Claim/Verifier）已于 2026-09-03 移除（原因见上方"当前状态"），相关设计文档只作为废弃历史保留。

## 文档职责

| 文档 | 职责 |
|---|---|
| 路线图 | 阶段顺序、目标、边界和门禁 |
| 总体目标架构 | 跨阶段模块边界、数据主线和全局约束 |
| 当前阶段设计 | 当前阶段为什么这样设计、接口和异常策略 |
| 当前阶段实施计划 | 精确文件、函数、测试、任务顺序和验证命令 |
| `backend/README.md` | 安装、配置、目录和运行方式 |

每次只为当前阶段维护一份设计和一份实施计划。已完成阶段的文档保留为历史记录，不用于覆盖当前架构。

## 已完成阶段资料

- [阶段 1 说明](stages/01-cli-single-agent.md)
- [阶段 2 设计](superpowers/specs/2026-08-30-stage-02-langgraph-context-compression-design.md)
- [阶段 2 实施计划](superpowers/plans/2026-08-30-stage-02-langgraph-context-compression.md)
- [模块化目录设计](superpowers/specs/2026-08-31-deeptrace-module-layout-design.md)
- [模块化目录重构计划](superpowers/plans/2026-08-31-deeptrace-module-layout-refactor.md)
- [阶段 3 规划式 Deep Research 设计](superpowers/specs/2026-09-01-stage-03-planned-deep-research-design.md)
- [阶段 3 实施计划](superpowers/plans/2026-09-01-stage-03-planned-deep-research.md)
- [阶段 3 研究质量加固设计](superpowers/specs/2026-09-01-stage-03-research-quality-hardening-design.md)
- [阶段 3 研究质量加固计划](superpowers/plans/2026-09-01-stage-03-research-quality-hardening.md)

## 已移除阶段资料（废弃历史）

阶段 4（Evidence/Claim/Verifier）于 2026-09-03 经项目所有者决策移除，源码与测试已删除。以下文档仅为决策记录保留，**不反映当前架构**，当前能力是"阶段 1-3 规划式研究 + 阶段 5 的 Memory/API/Web UI"。

- [阶段 4 Evidence Store 与 Verifier 设计](superpowers/specs/2026-09-01-stage-04-evidence-verification-design.md)
- [阶段 4 实施计划](superpowers/plans/2026-09-01-stage-04-evidence-verification.md)

## 维护规则

- 以路线图和总体目标架构作为长期事实来源。
- 以最新阶段设计和实施计划作为当前开发依据。
- 实现完成后同步更新状态、目录结构和运行命令。
- 不复制同一设计到多份文档，避免内容漂移。
- 文档和示例不得包含真实 API Key。
