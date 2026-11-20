# Agent 评测：版本回归与策略比较

本轮在现有 Agent 评测框架上，补齐独立的跨版本/跨策略回归入口、显式验收策略、评分溯源与失败报告。服务于项目内部迭代，不新增平台服务或生产依赖。

后续已执行真实模型实验，并修正真实入口的执行 profile 与评分传输配置，见[真实评测记录](../2026-11-07-real-evaluation/README.md)。本页原始合成示例和 verification.json 保留为上一阶段的历史验证，不覆盖成新的真实质量成绩。

已有的 30 道冻结资料题覆盖六类能力，按来源组分为 12 道开发题与 18 道测试题；题目/参考经过 Agent 来源核验，仍未完成独立人工金标审查。数据集规模、工程测试数量和真实模型实测数量必须分别说明。

## 能力与边界

| 环节 | 当前实现 |
| --- | --- |
| 任务资产 | 原有问题、成功要求、参考事实、引用位置、来源哈希和开发/测试切分 |
| Agent 执行 | 原有 Workflow、Plan-and-Execute、Multi-Agent、固定检索 Baseline；独立运行状态、预算、轨迹与证据留存 |
| 质量评分 | 原有独立 Ragas 评分及论断/引用评分；新回归入口可合并不重叠的指标文件 |
| 实验校验 | 校验 manifest、实际受评输入、评分模型/实现/配置、资料与元数据身份 |
| 版本回归 | 同策略的两个实验可比较代码版本；同一实验或不同实验可选择不同策略比较 |
| 统计 | 复用按题配对的 percentile bootstrap，先题内平均重复，再比较题间差值，报告 CI95 |
| 验收 | 显式策略检查平均退化、单题退化、评分覆盖、独立题数、完成/回答率和可选延迟比 |
| 结果 | JSON、Markdown、原始 trial ID、逐题改善/退化/排除、Token 完整性与耗时 |

核心源码：

- `backend/src/deeptrace/eval/analysis_inputs.py`：比较命令共享的评分输入和身份校验。
- `backend/src/deeptrace/eval/regression.py`：实验可比性、矩阵完整性、统计复用与验收判定。
- `backend/src/deeptrace/eval/regression_cli.py`：离线命令行入口。
- `backend/src/deeptrace/eval/regression_report.py`：人可读报告及原始 trial 索引。
- `backend/evaluation/ragas_quality.py`：补入共享评分实现哈希；共享实现改变时拒绝复用旧评分身份。

## 使用方式

以下命令均从仓库 `backend` 目录执行。回归命令只读取已保存的 Agent/评分结果，不加载 `.env` 或调用模型。

### 1. 立即体验三个可复现的验收分支

本目录 `controlled/` 保存手工构造的输入和评分，仅测试门禁行为。不存在真实模型成绩，也没有把工程覆盖率换算为事实正确率。

```powershell
.venv/Scripts/python.exe -m deeptrace.eval.regression_cli `
  --baseline ../docs/benchmarks/2026-11-07-evaluation/controlled/baseline/quality_eval.json `
  --candidate ../docs/benchmarks/2026-11-07-evaluation/controlled/pass/candidate/quality_eval.json `
  --baseline-scores ../docs/benchmarks/2026-11-07-evaluation/controlled/baseline/scores/scores.json `
  --candidate-scores ../docs/benchmarks/2026-11-07-evaluation/controlled/pass/candidate/scores/scores.json `
  --metadata ../docs/benchmarks/2026-11-07-evaluation/controlled/baseline/metadata.json `
  --baseline-mode workflow --candidate-mode workflow `
  --policy ../docs/benchmarks/2026-11-07-evaluation/controlled/policy.json `
  --seed 7 --out ../tmp/evaluation-pass-new
$LASTEXITCODE
```

将两处 `controlled/pass/candidate` 改成 `controlled/fail/candidate` 或 `controlled/inconclusive/candidate`，同时使用新的输出目录，可以分别重现退出码 1 和 2。

| 分支 | 人工设定输入 | 预期结果 | 原始报告 |
| --- | --- | --- | --- |
| pass | 两题 0.5/1.0 → 0.75/1.0 | 退出 0 | [PASS](controlled/pass/report/regression.md) |
| fail | 两题 0.5/1.0 → 1.0/0.75；单题退化容忍 0.1 | 均分虽提高 0.125，第二题退化 0.25，退出 1 | [FAIL](controlled/fail/report/regression.md) |
| inconclusive | 候选第一题评分出错；要求完整覆盖 | 保留错误，不填 0；仅一题可配对，退出 2 | [INCONCLUSIVE](controlled/inconclusive/report/regression.md) |

每个 JSON 报告保存输入/评分/策略哈希、完整策略、裁判身份、题级差值和原始运行 ID。演示 manifest 的模型、依赖、源码值都是测试夹具，不代表真实服务或真实 Agent 的实验身份。

### 2. 接入现有真实实验

输入采用原有 runner 输出的 `quality_eval.json` v2；评分采用独立环境输出的 `quality_scores.json`、`claims_scores.json`，各评分目录必须保留对应 `identity.json`。元数据采用相同题集的 analysis card。

```powershell
.venv/Scripts/python.exe -m deeptrace.eval.regression_cli `
  --baseline ../tmp/baseline/quality_eval.json `
  --candidate ../tmp/candidate/quality_eval.json `
  --baseline-scores ../tmp/baseline-ragas/quality_scores.json `
  --baseline-scores ../tmp/baseline-claims/claims_scores.json `
  --candidate-scores ../tmp/candidate-ragas/quality_scores.json `
  --candidate-scores ../tmp/candidate-claims/claims_scores.json `
  --metadata ../tmp/assets/analysis-dev.json `
  --baseline-mode workflow --candidate-mode workflow `
  --policy src/deeptrace/eval/data/policies/regression-v1.json `
  --out ../tmp/version-regression-new
```

策略比较时，两个输入可以指向同一实验，分别选择 `baseline`、`workflow`、`plan_execute` 或 `multi_agent`；参数必须对应 manifest 中实际声明的策略。

资料题的 analysis card 可通过原有入口生成：

```powershell
.venv/Scripts/python.exe -m deeptrace.eval.assets --out ../tmp/assets-new
```

创建新的真实 Agent 实验和裁判评分仍使用原有运行/评分命令及各自的显式调用上限。新回归命令不自动启动这些付费步骤。

## 比较约束

受控门禁要求冻结本地语料、关闭长期记忆，并检查模型、数据、预算、输出长度、上下文政策、证据政策、Python/关键依赖版本及重复次数一致。允许源码快照和所选策略不同。模型比较、预算扩容实验、记忆收益、联网评测需要单独实验设计，当前门禁会拒绝混用。

每个选中策略必须完整覆盖 analysis card 的题目和 `0..repeats-1`；导出记录还必须与 manifest 的全部 sample ID 对应。不能删掉失败题，变成较小的成功样本。不同题集/切分/数据类型分组报告，不混合成一个平均数。

同一门禁指标的两边必须使用相同裁判身份与评分配置，包括导出的评分源码哈希、模型及论断/引用数量上限。评分调用预算差异本身不当作评分语义差异，但可能导致缺失指标，并受到覆盖门禁约束。

输入 JSON 拒绝非有限数、重复键、超过 64 MiB 的文件。输出必须使用空目录，拒绝符号链接输出和覆盖既有结果。哈希检查证明内容关系一致，不是数字签名，也不保证提供方身份、人工金标准或裁判准确性。

## 策略与统计口径

`src/deeptrace/eval/data/policies/regression-v1.json` 是明确标注 **example-uncalibrated** 的配置示例，不是行业标准或已经校准的发布线。正式使用前应在开发集及人工复核样本上确定容忍度，并在验收前冻结策略。

- `min_paired_tasks`：每个分组至少需要多少个独立题；重复次数不会增加题数。
- `min_score_coverage`：双方有效评分运行占全部运行的最低比例。
- `metrics.<name>.max_drop`：按题配对的平均质量下降容忍值。
- `metrics.<name>.max_task_drop`：可选单题退化容忍值，防止平均提升掩盖明显退化。
- `max_completion_rate_drop` / `max_answered_rate_drop`：执行终态和输出可用性门禁，**不等同于任务语义成功率**。
- `max_latency_ratio`：可选实测 p50 耗时比上限；不构成延迟显著性结论。

当前支持 AgentGoalAccuracy、FactualCorrectness、Faithfulness、论断证据支持度、引用准确性五个质量维度，沿用各自现有评分口径。缺失、error 和 N/A 保留，不填 0。报告同时留存 all-output 和 completed-only 视图；门禁使用 all-output，不只看成功运行。

验收采用配置的**观测平均差容忍度**，CI95 用于表达题间不确定性。`pass` 表示在当前样本/策略下没有发现超阈值退化，不代表统计非劣效证明、绝对质量合格或总体能力提升。双方都很差也可能没有相对退化。

退出码：0=通过；1=观察到超阈值退化；2=输入无效或证据不足。无效输入不写报告；证据不足会写 `inconclusive` 报告。已发现的退化优先于证据不足，两类检查均保留，可供 CI 阻止静默放行。

## 本轮验证与可用简历描述

实际执行的三种策略及 Baseline 离线矩阵为 **3 题 × 4 配置 × 2 次重复 = 24 次**，全部完成。[工程报告](scripted-matrix.md)与[身份/原始文件哈希](scripted-matrix-summary.json)保留在本目录；完整本地记录位于 `tmp/evaluation-20261107/scripted-matrix`。这是合成 smoke 资料和脚本模型的工程验证，不是 24 个真实模型质量样本。

门禁三个分支实际退出码见 [controlled-results.json](controlled-results.json)。自动测试覆盖跨版本控制一致性、评分身份、完整任务矩阵、缺失指标、题内重复、平均提升掩盖单题退化、失败运行分母、资源缺失值及 CLI 输出/覆盖保护。

本轮最终验证：后端离线全量 **1603 passed / 2 real tests deselected**（82.98 秒），独立评分环境 **67 passed**（4.95 秒）。本轮生产源码的 Scoped Ruff E/F/I/UP/B/SIM/C4 检查（不检查行宽）、相关测试的 F/I 检查与改动空白检查通过。原有 GitHub Actions 后端测试会包含这些新回归测试，但本轮未触发或核实远端 CI；没有执行真实模型或真实裁判调用。

复核检查正确性、可读性、架构、输入/输出边界及有界处理。发现并修复两处问题：Ragas 共享评分实现原先未进入评分身份；声明的题目×重复次数需要在展开前限制为至多 10000。均有先失败、后通过的回归测试。最终文件哈希与验证命令见 [verification.json](verification.json)。

适合写进简历的表述：

> 构建 DeepResearch Agent 评测与回归框架，支持 Workflow、Plan-and-Execute、Multi-Agent 与检索 Baseline 对照；基于版本化任务集、实验快照和独立质量评分，实现题级配对分析、Bootstrap 置信区间及可配置回归门禁，提供缺失评分阻断、单题退化定位和结果溯源。

需要量化工程验证时，可补充：

> 建设包含 30 道真实来源资料题、六类能力及 12/18 开发测试切分的评测资产，完成 24 次离线策略矩阵验证；通过完整输入/裁判配置哈希与原始轨迹留存支持可复现实验。

面试时应说明：30 道题是现有资产，不是本轮新增或全部真实实测；参考仍待独立人工复核。没有本轮真实质量提升、商业产品优胜、官方榜单排名或线上成功率数字。真实多题基线、裁判与人工一致性校准、正式冻结测试验收、线上失败反馈及远端 CI 执行仍需后续分别验证。
