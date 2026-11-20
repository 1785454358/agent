# Harness 调研后的第二轮：有界范围审查

**结论：保持原子规划为默认，范围审查仅保留为显式实验选项。** 两种候选都没有通过原质量门禁，未用更高完成率或单项引用分数替代整体结论。调研、实现、44 次真实 Agent 试跑和失败归因均已完成；这不是已发布的质量提升。

## 调研带来的取舍

对照了 [Deep Agents v0.7](https://www.langchain.com/blog/deep-agents-v0-7) 的轻量基础提示及可选待办、[Anthropic 长运行 harness](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) 的任务清单/进度/验证分离、[Open Deep Research](https://github.com/langchain-ai/open_deep_research/blob/1b7d2e80db9faa586165c60e09096dbbfd483a64/src/open_deep_research/deep_researcher.py) 的研究简报与执行分层，以及 [DeerFlow](https://github.com/bytedance/deer-flow/blob/f68abbb8314f833929df88cde05d81310da27783/README.md) 的通用任务组织。完整资料与本项目推断见 [调研说明](../2026-11-07-harness-contract/research.md)。

这些项目没有在本项目的模型、任务和预算下接受比较，因此不能据此排“最佳 harness”。本轮固定模型做两个具体实验，并保留反例。当前证据支持按模型和失败模式选择机制，不支持默认增加规划或审查层。

## 实现

上一轮 [聚合契约候选](../2026-11-07-harness-contract/README.md) 虽减少补查，却遗漏必要前提，已移除其配置选项。第二版保留原子需求，增加初始封存前的一次可选范围审查：

```mermaid
flowchart LR
  Q[完整用户问题与约束] --> P[原子规划]
  P --> R[可选范围审查]
  R --> H[宿主校验 ID 与原句摘录]
  H --> S[检索与原文读取]
  H -->|失败时保留原计划| S
  S --> E[严格证据与覆盖校验]
  E --> W[写作与事实复审]
```

- 只可保留、收窄或排除原 ID；要求所有原 ID 恰好被交代一次，至少保留一项。
- 保留项需给出用户问题或约束中的逐字摘录。宿主据此检查结构可追踪性，**不能据此证明语义范围正确**。
- 重编号并同步 query targets，只移除所有目标都被排除的检索分支；保留来源政策、用户约束和存活分支说明。
- 失败、格式不合法、ID/摘录不匹配时保留原分解计划。没有证据仍不能标为已覆盖。
- 在 Workflow、Plan-and-Execute、Multi-Agent 的初始规划边界共用；最多新增一次模型调用，计入原来的共享预算，没有隐藏重试。

默认配置仍是 `DEEPTRACE_RESEARCH_COMPLETION_SCOPE=decomposed`。`scope_review` 是本轮未通过回归的实验配置，不建议作为当前模型的默认。

## 真实对照结果

第一阶段重新跑 12 题基线、12 题聚合候选及 6 次其他策略探针；第二阶段复用完全相同的基线字节与评分，再跑 12 题范围审查候选及 2 次其他策略探针。合计 **44 次新 Agent 试跑**，并非 44 道不同题目。全部为固定 dev 资料题，每种配置每题一次，18 道 test 题未参与调优。

三组使用相同模型 `deepseek-v4.1-flash`、禁用 thinking、同一资料/参考答案，以及相同 Ragas 与 claims-v3。每次仍限 20 次模型调用、48 次工具调用、30 次 Provider 尝试、240 秒、3072 输出 tokens、2500 字符答案。第二阶段不重新抽取更有利的基线。

| 指标 | 新基线 | 聚合候选（已移除） | 范围审查（实验） |
| --- | ---: | ---: | ---: |
| completed，执行指标 | 11/12 | 12/12 | 10/12 |
| answered，执行标记 | 9/12 | 11/12 | 8/12 |
| 目标达成评分 | 0.833（12） | 0.833（12） | 0.750（12） |
| 参考事实 F1 | 0.642（12） | 0.539（12） | 0.557（12） |
| Faithfulness | 0.925（8） | 0.945（7） | 0.912（8） |
| Claim groundedness | 0.969（8） | 0.935（7） | 0.925（8） |
| 引用分数 | 0.945（12） | 0.927（12） | 0.956（12） |
| 模型调用 | 82 | 77 | 96 |
| 工具调用 | 194 | 142 | 191 |

括号是实际可评分题数。F1 是与参考论断的匹配分数，不能解释为事实准确率；正确但无关的扩写也会影响它。完成、answered 和来源命中均不等于语义任务成功。

范围审查的 F1 配对差为 **-0.0850，CI95 [-0.2183, 0.0408]**；目标评分差为 -0.0833。引用分数差为 +0.0104，CI95 [-0.0722, 0.0938]，不能宣称显著改善。保持原来的 example-uncalibrated 门禁策略，结论为 **fail，退出码 1**；Faithfulness 覆盖不足仍为 inconclusive，没有降低阈值。

[完整门禁](gate/regression.md)、[逐题/原始契约与审查响应](results.json)、[全部原始答案](answers/)、[评分及身份](scoring/) 均保留。两个定向策略探针一项 completed、一项 partial，没有独立质量评分，不能替代主矩阵。

## 定位到的失败机制

1. **聚合检查过粗。** 第一版实际漏掉 interrupt 载荷的 JSON 序列化前提，并出现恢复位置的不准确表述，因此撤回。
2. **审查模型复述原偏差。** 第二版 14 次执行中，12 次实际触发审查；10 份结构有效，却全部保留原有 ID。比较题仍要求两种 API 的完整迁移路径，审查并未识别主要的范围扩张。
3. **结构约束确实有边界作用。** 两份审查因 ID/摘录等校验失败而保留原计划；另两次初始计划已降级，未再调用审查。`version_boundary-dev-02` 把省略号写进声称逐字复制的摘录，被宿主拒绝。逐字匹配有助审计，却不能证明保留的需求真的必要。
4. **必要前提恢复后仍有虚假缺口。** 第二版暂停题已经完整列出三个前提，但仍把未问的最低版本等内容作为缺口。多加一个审查角色没有稳定解决写作冗余与语义覆盖问题。

详见 [结构回放与 Agent 审查](review-audit.json)。没有用这些意见覆盖任何裁判分数，也没有人工标签或“全部审查正确”的声明。后续应优先研究按题型精简规划上下文、输出相关性和必要条件保留，并重新做受控实测；本轮没有实现或验证这些后续候选。

## 验证、资源与复现

最终源码 **1627 passed，2 deselected**，定向测试 61 passed，变更源码/测试及驱动的代码检查通过。独立评分器与基线身份一致，本阶段 36 个 Ragas 指标和 24 个 claims 指标均无 error；不可评分项保留 N/A，没有填零。

两阶段合计实际 **919 次 Provider 请求**，包含 Agent 与独立评分调用；第二阶段复用基线不重复计费或计数。费用未知，没有推算价格。详细输入/输出 tokens、源码快照、控制变量、裁判身份见 [verification.json](verification.json) 和上一阶段 verification.json。

[reproduction-inputs.zip](reproduction-inputs.zip) 保存完全相同的基线输入及评分、新候选/探针输入、全部原始模型/工具轨迹、源码快照、metadata、原门禁策略和测试。解压到新目录，从 backend 执行：

```powershell
.\.venv\Scripts\python.exe -m deeptrace.eval.regression_cli `
  --baseline <目录>/baseline/quality_eval.json `
  --candidate <目录>/candidate/quality_eval.json `
  --baseline-scores <目录>/baseline/ragas/quality_scores.json `
  --baseline-scores <目录>/baseline/claims/claims_scores.json `
  --candidate-scores <目录>/candidate/ragas/quality_scores.json `
  --candidate-scores <目录>/candidate/claims/claims_scores.json `
  --metadata <目录>/metadata.json --policy <目录>/policy.json `
  --baseline-mode workflow --candidate-mode workflow --seed 7 `
  --out <新的空目录>
```

预期退出码 1，完全离线。摘要和比较应与本目录 gate 报告一致。`run_experiment.py` 是真实付费驱动，不应无意重跑。上游调研与全部交付文件的索引见 sources.json、artifact-index.json。

本实验仅一次 dev 运行，生成器、范围审查及独立裁判来自同一模型，多个候选使用了同一开发集，部分指标受输入上限影响。哈希证明一致性，不证明裁判正确或总体质量。这些限制不因测试通过而消失。

## 简历表述

> 构建可溯源的 Agent harness 对照评测，完成 44 次真实执行，结合原始轨迹、独立质量评分与单题回归门禁，识别“执行完成率提高但事实覆盖退化”的策略，阻止其替换默认配置；实现共享预算下的可选范围审查及严格失败回退。

可以讲调研、假设、反例和工程约束；不要把候选引用分数或执行完成率写成已发布产品的准确率提升。
