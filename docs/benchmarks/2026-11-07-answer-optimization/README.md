# 真实失败审查、修复与回归记录

本轮由 Agent 审查，没有新增人工复核要求。最终保留两处可定位、可复现的修复：证据评估的传输标记兼容，以及引用评分的代码/版本号切句。一次扩大提示词的候选未通过回归，已撤回；下面的候选质量提升不能当作当前产品的提升。

## 最终落地的修复

1. **完整证据判断被格式错误丢弃。** 旧真实轨迹中，部分模型在合法 JSON 中回显根字段 `"type":"json_object"`。严格 schema 因此拒收整份判断，补修也重复相同错误；已有发现最终丢失，`comparison-dev-01` 的 Workflow 只交付无证据兜底。现在仅移除 schema 未声明的这一精确传输标记，再执行原有严格校验。未知字段、其他 type、冲突、非法引用及来源资格校验均保留。
2. **评分器拿残句判断技术引用。** 旧评分会在代码中的句点处切句，例如把 `langgraph>=1.2`、`langgraph.types` 截成 `2`、`types`。现在句子定位复用代码掩码，保留行内代码/代码块中的标点，并保留普通文本数字版本中的小数点。评分器身份更新为 `claims-v3-prose-sentence-boundaries`，旧缓存不会冒充新结果。

最终差异见 [production-changes.patch](production-changes.patch)。规划、写作和最终自审的三个提示词文件已恢复到本轮开始时的原始字节内容。

## 真实验证证据

- 对旧实验三种策略的 **50 份**实际证据判断做离线回放：可解析数 **43 → 49**。修复了 6 份精确传输回显；剩余 1 份 `finding_ids` 类型错误仍被拒绝。见 [逐响应回放](protocol-replay.json) 与 [回放脚本](replay_protocol.py)。这表示结构兼容改善，不表示语义正确率。
- 撤回提示词后，用原失败题 `comparison-dev-01` 对三种策略各执行一次真实模型调用流程：三者均交付了带引用的核心比较，Workflow 为 completed，Plan-and-Execute 与 Multi-Agent 仍因额外规划缺口达到补查上限而 partial。原有失败没有被覆盖。见 [Workflow](answers/protocol-confirmation/comparison-dev-01/workflow.md)、[Plan-and-Execute](answers/protocol-confirmation/comparison-dev-01/plan_execute.md)、[Multi-Agent](answers/protocol-confirmation/comparison-dev-01/multi_agent.md)。这三次是定向确认，没有全量独立质量评分。
- 对新旧两版共 **24 份** Workflow 答案回放引用切句，8 份的判定输入发生修正。选取已定位的两个技术题，分别对优化前/候选答案做一次真实 v3 引用评分，共 **4 份答案、35 次 Provider 请求**，没有挑选重试的高分结果。见 [完整校准记录](citation-calibration.json)。
- 最终源码离线测试 **1612 passed，2 deselected**，独立评分器测试 **75 passed**，代码检查通过。本轮共 21 次新 Agent 试跑、4 份定向引用复评，累计 394 次 Provider 请求；用量完整记录，费用未知，没有推算价格。

| 切句校准对象 | 原 v2 引用分数 | 修复后 v3 引用分数 |
| --- | ---: | ---: |
| 原版 single_hop-dev-02 | 0.917 | 1.000 |
| 原版 version_boundary-dev-01 | 0.800 | 1.000 |
| 候选 single_hop-dev-02 | 0.750 | 0.833 |
| 候选 version_boundary-dev-01 | 0.556 | 1.000 |

这是评分输入修复的校准，**不是 Agent 质量提升**。v3 仍把候选中的部分引用判为不支持，没有强行修成满分。整轮 v2 分数和失败门禁保持原样；不能将上表混入整轮均值。

## 未通过并撤回的提示词候选

先审查原来的 12 份 Workflow 答案、对应资料和关键轨迹，区分核心正确但冗余、真正遗漏/API 错误、规划扩大范围与裁判问题，记录在 [review-notes.json](review-notes.json)。随后尝试收紧任务范围、语言/版本边界及写作篇幅。

候选运行全部 12 道冻结 dev 题的 Workflow，每题一次；另对 3 道题的两种其他策略做 6 次探针。模型仍为 `deepseek-v4.1-flash`，禁用 thinking；原资料、参考答案、工具与独立评分器均未改变。每次仍限 20 次模型调用、48 次工具调用、30 次 Provider 尝试、240 秒、输出 3072 tokens、答复 2500 字符；没有增加研究资源，也没有触碰 18 道 held-out test 题。

整轮前后比较使用相同的 Ragas/claims-v2 身份和输入上限，独立评分没有错误返回。以下是可评分题的均值，括号为覆盖题数：

| 指标 | 原 Workflow | 已撤回候选 |
| --- | ---: | ---: |
| 目标达成评分 | 0.917（12） | 0.833（12） |
| 参考事实 F1 | 0.566（12） | 0.643（12） |
| Faithfulness | 0.785（7） | 0.877（7） |
| Claim groundedness | 0.946（7） | 0.926（7） |
| v2 引用分数，含已发现的切句缺陷 | 0.950（11） | 0.896（12） |

参考事实 F1 的配对差为 +0.0767，按题 Bootstrap CI95 为 **[-0.0800, 0.2458]**，包含零；目标达成差为 -0.0833。F1 是参考论断的匹配指标，不能解释成“事实准确率提高 7.67%”。引用分数应使用共同可评分题配对：11 题差值 -0.0632，不能直接相减不同覆盖范围的均值。

未修改的示例门禁结论为 **fail，退出码 1**：目标达成与单题 F1/引用下降触发失败，Faithfulness 因覆盖不足为 inconclusive。门禁策略本身标注 example-uncalibrated；其失败结果仍如实保留，并据此撤回候选提示词，没有换阈值或改参考答案。[完整门禁](gate/regression.md)、[机器结果](gate/regression.json)、[逐题结果](results.json)、[候选源码差异](rejected-candidate-changes.patch) 均可查看。

新旧源码快照可区分具体版本，但这轮同时改变协议和提示词，没有独立消融，不能将某一分数变化归因于其中一项。

## 仍然存在的问题

- 规划仍会把比较题扩成对称实现细节，消耗补查预算。最终定向确认中另外两种策略仍为 partial；本轮没有将其伪装成全部完成。
- 遗漏必要边界和多写无关事实仍会发生。撤回候选意味着其部分修正示例不能算作产品已解决；跨语言 API 混用仍需后续受控优化。
- `multi_hop-dev-01` 的候选漏写 namespace 示例不等于授权保障这一边界；这是应保留的退化信号。另一个目标评分在 `comparison-dev-02` 中把“定性取舍”与“包含取舍的表格比较”判成不匹配，Agent 审查认为可疑，但没有覆盖其零分。[原始裁判诊断](goal-judge-diagnostics.json) 区分这两种情况。
- 一些选中资料超出独立评分器的 100k 字符上限，Faithfulness/groundedness 只覆盖 7/12；N/A 没有填零，也没有按完整覆盖宣称结果。
- 自动裁判与生成器使用相同模型，且每题仅一次 dev 运行。本轮没有证明总体质量或统计显著性，也没有用 Agent 审查替换人工标签。
- v3 目前有定向真实校准，未对整轮历史矩阵重评。后续全量比较应统一使用 v3 的新身份，不能复用 v2 门禁作为 v3 通过证明。

## 复现与审计

[reproduction-inputs.zip](reproduction-inputs.zip) 包含完整的原版/候选质量输入（带原始模型与工具轨迹）、原始独立评分及身份、共同 metadata、原门禁策略、候选源码快照、保留前文件、最终定向确认和 v3 修复材料。[verification.json](verification.json) 记录测试、哈希和最终状态；[artifact-index.json](artifact-index.json) 索引交付文件。

解压到一个新目录，在 backend 使用现有离线回归入口，不需要模型密钥即可重现**已撤回候选**的失败结论：

```powershell
.\.venv\Scripts\python.exe -m deeptrace.eval.regression_cli `
  --baseline <解压目录>/before/quality_eval.json `
  --candidate <解压目录>/after/quality_eval.json `
  --baseline-scores <解压目录>/before/ragas/quality_scores.json `
  --baseline-scores <解压目录>/before/claims/claims_scores.json `
  --candidate-scores <解压目录>/after/ragas/quality_scores.json `
  --candidate-scores <解压目录>/after/claims/claims_scores.json `
  --metadata <解压目录>/metadata.json --policy <解压目录>/policy.json `
  --baseline-mode workflow --candidate-mode workflow --seed 7 `
  --out <新的空输出目录>
```

`run_candidate.py` 与 `run_final.py` 保留实际运行的驱动文件和哈希，会产生真实付费请求，不应用于无意重跑。旧实验保存在 [上一轮记录](../2026-11-07-real-evaluation/README.md)。

## 可用于简历的表述

> 构建 Agent 自动化评测与回归体系，覆盖真实模型执行、证据与引用评分、按题配对比较及评分溯源；基于真实失败轨迹修复证据协议兼容与技术引用切句问题，并通过回归门禁识别、撤回存在单题退化的提示词优化。

可以讲清 12 题四配置基准、12 题跨版本候选与失败定位过程。不要把已撤回候选的 F1 均值或评分器修复后的分数写成当前产品的准确率提升。
