# DeepTrace 文档入口

## 当前状态

- 阶段 1：已完成
- 阶段 2：已完成
- 阶段 3：已完成（真实 LLM、Tavily、网页抓取和本地 BGE-M3 冒烟通过）
- 阶段 4：待开始
- 当前代码目录：`backend/`

## 当前阅读顺序

1. [六阶段演进路线图](roadmap/deeptrace-evolution.md)
2. [总体目标架构](architecture/deeptrace-target-architecture.md)
3. [阶段 3 规划式 Deep Research 设计](superpowers/specs/2026-09-01-stage-03-planned-deep-research-design.md)
4. [阶段 3 实施计划](superpowers/plans/2026-09-01-stage-03-planned-deep-research.md)
5. [后端运行说明](../backend/README.md)

阶段 3 设计与实施计划现作为已完成实现的事实来源。下一阶段是 Evidence Store 与 Verifier；在阶段 4 设计和计划明确前，不提前实现 Memory、API、Web UI 或规模化评测。

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

## 维护规则

- 以路线图和总体目标架构作为长期事实来源。
- 以最新阶段设计和实施计划作为当前开发依据。
- 实现完成后同步更新状态、目录结构和运行命令。
- 不复制同一设计到多份文档，避免内容漂移。
- 文档和示例不得包含真实 API Key。
