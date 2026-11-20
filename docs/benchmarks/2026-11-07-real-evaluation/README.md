# 真实模型评测：冻结资料策略矩阵与联网补测

这轮使用配置的真实 `deepseek-v4.1-flash` 服务执行 Agent，并在独立 SDK 环境中调用真实模型评分。没有用 scripted 模型替代正式答案，没有手写真实质量分数。研究服务和裁判使用同一配置模型，属于独立评分流程下的同模型自评，不是独立专家评价。

## 实验范围

- 主实验：已有冻结资料开发集的全部 12 道题，覆盖六类能力；Workflow、Plan-and-Execute、Multi-Agent 和固定检索 Baseline 各一次，共 48 次正式运行。18 道保留测试题未用于本轮调试。
- 联网补测：SQLite WAL 与 LangGraph 记忆/恢复两道题，Workflow 各一次，实际执行 Tavily 搜索和网页抓取。问题及评分参考在运行前固定，见 [live-tasks.jsonl](live-tasks.jsonl) 与 [reference card](live-reference-card.json)。联网成绩不混入冻结题集。
- 默认批量研究执行器；正式主实验每次最多 20 次模型调用、48 次工具调用、30 次 Provider 尝试、240 秒、3072 输出 Token。问题级并发最多 3，首题作为串行校准，策略顺序固定。
- 研究与评分分别计量。主实验裁判请求限额为 Ragas 480 次、论断/引用评分 800 次；引用最多检查 12 个使用点，论断最多 40 条，超限会在评分详情中标注采样。
- 本地原始文件根目录：`tmp/real-evaluation-20261107`。正式实验分别位于 `research-batch/` 和 `live/`；输入、逐条记录、模型消息、工具结果、证据和 usage 均保留。

## 真实执行结果

| 配置 | 正式运行 | completed 状态 | answered 标志为真 | p50 秒 | 模型请求 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 12 | 10 | 10 | 11.70 | 24 |
| Workflow | 12 | 11 | 9 | 30.22 | 78 |
| Plan-and-Execute | 12 | 9 | 9 | 33.82 | 82 |
| Multi-Agent | 12 | 10 | 10 | 32.89 | 84 |

主实验共 40 次 completed、8 次 partial，268 次研究模型请求，已观测输入 1,004,378 Token、输出 120,695 Token。这里的 completed/answered 均是系统运行标志，**不是任务语义正确率**。部分证据不足题正确拒绝编造数字，仍可能被系统标记 answered=false，不能据此直接判定语义失败。

全部 50 次正式输出见 [answers](answers)，机器可读执行数据见 [execution-summary.json](execution-summary.json)。[主实验 manifest](research-batch-manifest.json) 和 [联网 manifest](live-manifest.json) 固定模型、数据、源码、预算及执行 profile。p50 是本机该配置下的观测值，期间存在并发模型请求和离线检查，不能当作专用环境的性能排名。

质量评分、按题对照及门禁结论见 [quality-summary.md](quality-summary.md)、[配对分析](comparison/comparison.md) 与 [gate-decisions.json](gate-decisions.json)。评分以各指标的有效样本数为分母，N/A 和 error 原样保留。主实验有 27 次运行选入的证据全文超过既有 100000 字符评分输入限制，因此部分 Faithfulness/论断支持度无法评分。没有按 gold 位置裁剪资料或把这些缺失补成 0/1。

## 独立评分结果

以下为同模型裁判的开发集校准结果；括号为有效评分数/该策略总运行数。FactualCorrectness 是对评分参考的论断 F1，不等于人工验证事实准确率。

| 策略 | 目标完成评分 | 事实 F1 | 引用支持评分 |
| --- | ---: | ---: | ---: |
| Baseline | 0.667（12/12） | 0.491（12/12） | 0.867（12/12） |
| Workflow | 0.917（12/12） | 0.566（12/12） | 0.950（11/12） |
| Plan-and-Execute | 0.833（12/12） | 0.535（12/12） | 0.874（12/12） |
| Multi-Agent | 0.750（12/12） | 0.591（12/12） | 0.877（11/12） |

主实验 Ragas 完成 144 个指标项（117 个有效、27 个 N/A），论断/引用评分完成 96 个指标项（67 个有效、29 个 N/A）；正式主实验没有解析 error。Baseline 的 Faithfulness 与论断支持度为 0/12 可评，其余三种策略各为 7/12，**无法据此比较这些维度相对 Baseline 的增益**。

Workflow 目标完成评分的按题配对差值为 +0.250，95% bootstrap 区间 [0.000, 0.500]；事实 F1 差值 +0.075，区间 [-0.083, 0.222]。Workflow 引用支持度在 11 对有效题上的差值 +0.080，区间 [0.009, 0.167]，但仍有一题缺失且未经人工裁判校准，不能当作总体显著性或发布合格证明。所有策略/维度的原始差值和排除数均在配对分析中保留。

未调整既有 `example-uncalibrated` 策略以迎合实测：三个复杂策略相对 Baseline 的示例门禁均返回 fail。原因包含单题退化超阈值、完成/回答标志变化、实测 p50 超过 1.25 倍，以及部分指标覆盖不足；失败与证据不足检查分别记录。平均提升没有覆盖掉单题退化。具体见 [Workflow](gates/workflow/regression.md)、[Plan-and-Execute](gates/plan_execute/regression.md)、[Multi-Agent](gates/multi_agent/regression.md)。这不是已经校准的正式发布判定。

主实验 Ragas 使用 330 次 Provider 尝试，输入 626,433 / 输出 150,376 Token；论断/引用评分使用 438 次，输入 5,336,385 / 输出 11,943 Token。与研究阶段分开计量，缺少可靠费率时费用保持 null。初始校准中断的用量另行保留，不伪装成已完整核对的总体费用。

联网补测两题均交付答案；SQLite 引用支持评分 1.000，LangGraph 为 0.917，均为最多 12 个引用使用点的自动核验。联网 Ragas 的两处截断错误保留为 error，未混入正式主实验或以 0 代填。

## 校准过程与保留的失败

### 评测入口与默认产品路径不一致

最初沿用的 eval runner 固定装配工具循环，而产品默认装配批量研究。工具循环首题四个配置留下 4 条已结束记录，另有 3 条运行中的 claim。确认路径不一致后停止了该身份，没有删除失败或 stale claims，也没有把它们算进正式批量路径成绩。

原始目录为 `tmp/real-evaluation-20261107/research`，说明见其中 `aborted.json`，原驱动保存为 [run_research_legacy.py](run_research_legacy.py)。4 条已保存记录包含 58 次 Provider 尝试；对 3 条中断运行各保守预留 30 次，合计预留 148 次。因此正式新实验把研究 Provider 上限从原有 900 降为 752，没有通过换目录重置这部分额度。中断运行的精确 Token 和总调用次数未知，不能把总体账单写成已完整核对。

已补 `runtime_settings` profile：真实 CLI 采用与产品相同的 batch executor、来源选择参数、上下文窗口、最终事实审查及页面上限；工具循环保留供原有确定性测试和显式对照使用。执行 profile 进入 manifest，门禁拒绝跨 profile 混比。评测仍使用独立内存状态、冻结检索及评测计数器，不声称测到了生产数据库恢复或真实长期记忆收益。

### 裁判传输与结构化输出上限

联网评分试跑发现空响应和截断 JSON。初始评分器没有传递生产配置中的思考模式；已把 credential-free `request_options` 纳入裁判身份，并对真实请求验证 JSON/思考参数透传。

修复思考配置后，仍观察到部分 Ragas NLI 输出正好消耗 2048 Token、JSON 在字段中截断。于是为 Ragas 增加可配置的裁判输出上限，并确保参数真正到达 SDK；正式主实验统一采用 6144 Token，裁判源码与配置均进入身份。没有修改裁判评分规则、参考答案或发布阈值来提高成绩。

初始 `live-ragas/`、`live-claims/` 的错误、用量及中断记录保留。后续 `live-ragas-v2/`、`live-claims-v2/` 的请求上限分别从 32/64 扣除已发生的 7/16 次尝试，降为 25/48。联网 v2 中仍有 Ragas 截断错误，保留为 error；没有不断重新评分挑选高分。

正式主实验评分使用 `ragas/`、`claims/`。生成答案没有因为评分低或失败而重跑。原始研究代码保存在 `research-batch/source_snapshot/`，实际评分代码和锁文件保存在 `scoring-source-snapshot/`。

## 可复现入口

以下主实验驱动会发生真实付费调用，默认输出目录固定且拒绝覆盖既有实验；用于审查本轮实际执行方式，不应为重试失败擅自改目录反复调用：

```powershell
cd backend
.venv/Scripts/python.exe -u ../docs/benchmarks/2026-11-07-real-evaluation/run_research.py
```

评分使用独立环境。正式主实验实际命令如下，原始目录已存在时不应重新运行：

```powershell
.venv-ragas/Scripts/python.exe evaluation/ragas_quality.py `
  --input ../tmp/real-evaluation-20261107/research-batch/quality_eval.json `
  --out ../tmp/real-evaluation-20261107/ragas `
  --max-provider-attempts 480 --max-output-tokens 6144 --env-file .env

.venv-ragas/Scripts/python.exe evaluation/claims_quality.py `
  --input ../tmp/real-evaluation-20261107/research-batch/quality_eval.json `
  --out ../tmp/real-evaluation-20261107/claims `
  --max-provider-attempts 800 --max-claims 40 --max-citations 12 --env-file .env
```

实际启动时 Ragas 6144 使用的是该版本 CLI 默认值；上面的显式参数与身份记录一致。API key 未进入导出的 manifest、评分身份或公开报告。

## 已暴露的产品与评测问题

- 对实际轨迹做了额外的离线逐字片段送达审计：[delivery-diagnostic.json](delivery-diagnostic.json)。74 个“参考片段 × 运行”检查中，5 个未抓取、33 个已选入证据但完整原文未出现在写作输入、36 个完整可见、2 个没有 responder 无法判断。这不是 74 道独立题，也不表示未完整可见的片段对应答案必错；部分原文、转述或研究结论仍可能传递事实。
- 复杂记忆题中存在答案缺口与部分完成，不能用“调用结束”代替需求覆盖。
- [failure-diagnostics.json](failure-diagnostics.json) 列出 10 次非 completed 或 answered=false 的运行，其中 4 次出现研究阶段完成、最终答案审查仍报告不完整的分歧。这是内部阶段间的实测症状，未把 reason code 冒充外部质量金标。
- 证据不足题中的合理拒答与 operational answered 标志有差异，需要结合评分量表解释。
- 证据全文超过评分输入限制造成指标缺失；这是评测覆盖缺口，不能用有效子集均分声称全体质量。
- 评分裁判与研究模型同源、参考由 Agent 核验而未完成独立人工标注、每题每策略仅一次、题目集中在一个官方资料体系，因此不能声称统计显著提升或广泛主题泛化。
- 本轮后端离线全量 1606 passed / 2 real tests deselected，出现 2 条已观察到的 aiosqlite `Event loop is closed` 后台线程警告；不在本轮中声称已修复。独立评分环境新增传输与输出参数回归后 70 passed。真实成绩来自本轮实验目录，不来自 pytest 的通过数。

这轮结果适合证明“能够组织真实 Agent 对照实验、定位评测集成缺陷并如实报告质量与缺失”，不适合写成“复杂策略已全面超越 Baseline”。

## 简历表述

> 构建可复现的 Agent 评测与回归流程，基于 12 道冻结官方资料题完成三种研究策略及 Baseline 的 48 次真实模型对照，并补充 2 道联网端到端验证；接入五维自动评分、按题配对 Bootstrap 和单题退化门禁，留存原始答案、工具轨迹、预算及源码身份，定位并修复执行路径漂移和裁判调用配置缺陷。

需要量化质量时，必须同时写明本轮样本、同模型自动裁判、有效覆盖和单次运行，避免把 Workflow 的 0.917 目标完成评分改写成“线上成功率 91.7%”，或把引用评分 0.950 改写成“整体事实准确率 95%”。
