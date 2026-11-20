# Harness 调研与本项目的取舍

调研日期：2026-11-07。仅使用官方文章和官方仓库；仓库版本及下载文件哈希另见 sources.json。这里比较设计机制，不按星数或其他项目的跑分排名。

| 参考 | 核实到的机制 | 对本项目的判断 |
| --- | --- | --- |
| [Deep Agents v0.7](https://www.langchain.com/blog/deep-agents-v0-7) | 精简基础提示和工具描述；TodoListMiddleware 改为可选，报告其受测模型/任务中的结果 | 规划不是越多越好；本轮不增加另一份全局规划提示，也不把它的跑分当成本项目结果 |
| [Deep Agents harness engineering](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering) | 从实际轨迹定位失败；使用自验证和循环检测等针对性改动 | 沿用本地原始轨迹、失败归因和配对回归，避免凭观感宣称优化 |
| [Deep Agents 模型配置](https://www.langchain.com/blog/tuning-deep-agents-different-models) | 将提示、工具及 middleware 作为模型相关的 profile | DeepSeek 的行为必须实测；不能直接套用其他模型的默认配置或性能数字 |
| [Anthropic 长运行 harness](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) | 初始化环境、显式功能清单、增量进展记录、结果验证，跨 session 延续工作 | 区分任务完成条件与执行进度。本项目是研究 Agent，不照搬其编码环境或长 session 初始化流程 |
| [Open Deep Research 固定版本源码](https://github.com/langchain-ai/open_deep_research/blob/1b7d2e80db9faa586165c60e09096dbbfd483a64/src/open_deep_research/deep_researcher.py) | 独立研究简报、supervisor/researcher、完成工具、研究轮数上限、压缩与最终报告 | 借鉴简报与执行分层及有界结束；保留本项目更严格的原文支持与宿主预算，不照抄其重试/结束逻辑 |
| [DeerFlow 固定版本](https://github.com/bytedance/deer-flow/blob/f68abbb8314f833929df88cde05d81310da27783/README.md) | 将 skills、子 Agent、记忆和 sandbox 组合为通用长任务 harness | 属于更大的执行型产品范围。当前主要缺陷是研究完成契约，迁移整套工作台、文件执行和 sandbox 并不能直接解决它 |

## 从轨迹得到的根因

本项目已有模型/工具 Gateway、共享预算、来源读取、支持片段校验、事实复审和独立评分。问题不是缺少框架名称，而是 `seal_initial_plan` 会把模型生成的子问题直接封存为必答 requirements。

原失败题只要求比较两个 API 在两个场景的适用性。模型把它扩成完整迁移说明等额外需求；即使已经找到核心比较，后续仍为这些需求搜索和补查，最后达到轮数上限。上一轮收紧提示词的候选有单题退化，已撤回，所以本轮验证一个明确的程序边界。

## 第一版实验（已被真实结果否决）

将“完成原始用户任务”与“用于发现资料的子计划”分开：原问题全文和用户约束保持固定，检索查询、分支 objective 和来源建议继续用于取材；这些模型派生子问题不再独立扩大最终完成清单。用一个宿主生成的 aggregate requirement 表示完整用户任务，而不是把问题截断塞进标签。

这是本项目基于上述资料作出的设计推断。它不是某个上游项目已经证明有效的同款算法，也不能保证模型一定检查了所有子问题。原文支持校验、最终事实审查和多子问题真实测试仍然必需。

相比整体更换 harness，这个实验保留现有授权和预算边界；相比增加一轮范围审查，它不增加一次模型调用。代价是封存 coverage 的粒度变粗，必须用完整任务评分和反例检查防止“看起来完成”。

## 验证规则

先重新运行旧策略作为基线，再运行新策略，均为同一批 12 道冻结 dev 题、每题一次 Workflow。两组统一使用 Ragas 与修复切句后的 claims-v3，避免新旧引用评分器混用；另跑六次其他策略探针。模型、资料、参考答案、资源上限与最终事实复审保持一致，18 道 test 题不参与调优。

保留原始答案、调用量、单题退化、评分缺失和门禁结论，不靠修改阈值宣布成功。第一版实际出现必要前提遗漏，已移除这一配置选项，源码快照保留。下一版保留原子需求，增加封存前有界范围审查，使用原有共享预算，并重新独立评分。

2026-11-08 使用 Context7 `/langchain-ai/deepagents` 查询官方仓库文档，复核 v0.7 的待办可选配置，以及 middleware 可在模型请求或状态准备边界介入。这支持选择宿主审查边界，不代表上游文档证明本项目语义审查有效。
