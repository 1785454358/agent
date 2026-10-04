# 共享规划与补查目标：实现和真实复测

## 已实现的边界

三模式初始规划使用同一个有界契约，区分需要来源证明的答案要点与执行约束。可选 execution_constraints 只用于规划输出校验，不持久化、不授予权限，也不替代原始任务。真正的版本/法律限制仍是研究事实；完整原始问题和既有用户约束保持传递。

补查先验证目标全部属于主机封存要求，再按顺序保留当前 missing/conflicting 目标。混合 covered/gap 不再整条误丢弃；未知 ID、重复 ID、纯 covered、重复查询仍拒绝，坏任务不占去重名额。P&E 与 MA 共用解析；Workflow 只统一规划/评估指令，没有新增补查循环。证据门禁、持久化 v2、模型、评分及预算均不变。

## 离线验证与审查

- TDD 新用例初跑：20 failed / 6 passed，包含旧实现忽略非法约束、混合目标丢弃和缺少显式全集接口；未以导入错误代替行为复现。
- 相关规划、补查、上下文、证据及三模式集成回归：108 passed。
- 冻结源码完整后端回归：953 passed / 2 deselected（116.24 秒）；隔离 Ragas 回归：34 passed。
- 改动文件 Ruff check 通过，8 个文件 format --check 通过。最后从 backend 工作目录复核时发现三个测试 import 排序因 Ruff 自动推断 src 根目录而与仓库根目录运行结果不同；依据 show-settings 定位后，仅按 backend 的第一方分类整理测试导入，36 项定向回归通过。实现源码未变，没有把目录差异伪称逻辑修复。
- 一次完整回归在源码接口调整期间运行，952 passed / 1 failed；严格续跑测试因源码身份改变而拒绝续跑。保留该诊断，未放宽身份校验。冻结后该测试单跑 1 passed，随后完整回归全部通过。

按正确性、安全、可维护性、测试与兼容性审查：保留输入不变性、未知目标拒绝、完整任务约束、旧 metadata 缺省兼容和 checkpoint v2；规划逻辑放入小型共享模块，不重构无关 evaluator。类型校验不能保证语义拆解正确，需真实轨迹核验。工作树含先前改动，HEAD 为 686420b；HEAD 不代表全部实现，实验已保存逐文件哈希和完整源码快照。本轮未 blanket stage 或提交用户先前改动，实现留在当前工作树。

## 执行前登记（2026-10-02）

用户确认规格并以“开始”授权实施与本批真实调用。本登记写入后启动，不挑选最好的一次结果。

| 项目 | 固定值 |
| --- | --- |
| 研究批次 | planning-gap-real-answer-20261002 |
| 数据 | single_hop-dev-01 / multi_hop-dev-02 / version_boundary-dev-02，三道已用开发题 |
| 模式 | plan_execute / workflow / multi_agent，各题各一次，共 9 条；不新跑 baseline |
| 资料 | 7 篇真实官方文档的冻结本地语料，搜索/抓取为本地复现，LLM 为真实 API |
| 模型 | doubao-seed-2.0-lite，temperature=0，输出最多 4096 token |
| 输出 | Answer，最多 2000 字符；Report 不在本批 |
| 单运行上限 | 40 逻辑模型调用 / 80 Provider 尝试 / 24 工具入口 / 12 分支轮 / 360 秒 |
| 整批上限 | 360 逻辑调用 / 720 Provider 尝试 |
| 评分 | 隔离 Ragas 0.4.3，沿用旧模型与标准，最多 144 Provider 尝试 |

执行前加载并验证的规范化内容哈希：dataset `44da14cc98057d2aa763c0c2117147b71b13167ceeb63ee137aa12c4e0a69dec`；corpus `ffd9e00644024250f508a0d27054c3b96b68e4065b5f0a1ab520ac9648104b8f`，与原 analysis-card 一致。两个新目录均不存在，凭据仅验证存在，未导出。Gold 仅进入评分侧。

在 backend 下执行：

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 360 --max-batch-provider-attempts 720 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix planning-gap-real-answer-20261002 --out ../tmp/planning-gap-real-answer-20261002
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/planning-gap-real-answer-20261002/quality_eval.json --out ../tmp/planning-gap-real-answer-quality-20261002 --max-provider-attempts 144 --env-file .env
```

研究 manifest 身份为 `a3264dd6c217749ac1439110ed7fd0be6f9c042607a00f3ed2b1f5d7166cf78f`；185 份源码/锁文件/评测数据快照已逐份对照 manifest 校验 SHA-256。研究结束、评分期间再次运行 source_identity，185 份差异为 0。9 个 sample_id 由批次前缀 × 上述 question_id × mode 组成，完整列表保存在 manifest.json。

## 结果

研究 9 条全部结束，CLI 退出码 1：0 completed、6 partial、3 failed。partial 均有非空引用回答，failed 均无答案；不能把有引用当完成。研究实际 281 个逻辑调用、281 次 Provider 尝试，input=1,137,788 / output=97,680，usage 缺失 0，artifact_errors=0，费用无可靠价表仍为 null。运行期间未修改实现/HEAD，未重跑或扩预算。

| 题目 | 模式 | 状态 / 原因 | 逻辑 / Provider | 工具入口 | 纯待办轮 | 秒 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| single_hop-dev-01 | P&E | failed / execution_error（RequestLimitReached） | 40 / 40 | 19 | 17 | 147.32 |
| single_hop-dev-01 | Workflow | partial / insufficient_evidence | 22 / 22 | 9 | 8 | 86.39 |
| single_hop-dev-01 | MA | partial / insufficient_evidence | 20 / 20 | 9 | 6 | 91.42 |
| multi_hop-dev-02 | P&E | partial / iteration_limit | 35 / 35 | 16 | 14 | 231.05 |
| multi_hop-dev-02 | Workflow | partial / iteration_limit | 33 / 33 | 14 | 13 | 212.54 |
| multi_hop-dev-02 | MA | failed / execution_error（RequestLimitReached） | 40 / 40 | 24 | 14 | 46.63 |
| version_boundary-dev-02 | P&E | failed / execution_error（RequestLimitReached） | 40 / 40 | 20 | 17 | 181.40 |
| version_boundary-dev-02 | Workflow | partial / insufficient_evidence | 29 / 29 | 10 | 13 | 82.96 |
| version_boundary-dev-02 | MA | partial / max_follow_ups_reached | 22 / 22 | 7 | 9 | 95.43 |

纯待办轮定义：tool_calls 非空且全为 write_todos 的模型轮，共 111 / 281 = 39.5%；不是 111 次网页请求。工具入口也不等于网络请求。这里的冻结本地资料运行没有实时联网 Tavily 调用。

原生 report.md 的 answered 标志表示没有 response_partial_reason，不等价于非空 answer：本批 answered=0，但有非空回答=6/9，语义评分仍逐条包含它们。gold_coverage 只是找到了参考来源 URL，不是事实正确率或问题覆盖率；引用 ID 格式有效也不保证所引原文真的支持断言。

### 原生 Ragas 主质量指标

评分已结束，退出码 0；实际 46 / 144 次 Provider 尝试，input=136,997 / output=54,157，usage 缺失 0，费用 null。研究加评分合计 327 次尝试，input=1,274,785 / output=151,837，计量完整；未自动重评。裁判配置及 scorer_sha256 与旧批次一致：`69144d3c8faeb2f2c77bd68c5139e435baa94f2b19ddbcea2064246c80c17688`。

分数范围 0–1，括号为有效评分 / 总运行数；均值只针对可评分题。全部 27 个指标槽位：17 ok、10 N/A、0 error。N/A 包括三条无答案 × 三指标，以及 P&E 多跳完整 selected source body 超过既有 100,000 字符 Faithfulness 输入上限。没有临时裁剪正文，也没有给失败/N/A 补零。

| 模式 | completed | partial / failed | FactualCorrectness F1 | Faithfulness | AgentGoalAccuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| P&E（主模式） | 0/3 | 1 / 2 | 0.310（1/3） | N/A（0/3） | 1.000（1/3） |
| Workflow | 0/3 | 3 / 0 | 0.243（3/3） | 0.622（3/3） | 0.333（3/3） |
| Multi-Agent | 0/3 | 2 / 1 | 0.165（2/3） | 0.833（2/3） | 1.000（2/3） |

| 题目 | 模式 | F1 | Faithfulness | Goal |
| --- | --- | ---: | ---: | ---: |
| single_hop-dev-01 | P&E | N/A | N/A | N/A |
| single_hop-dev-01 | Workflow | 0.00 | 0.50 | 0 |
| single_hop-dev-01 | MA | 0.00 | 1.00 | 1 |
| multi_hop-dev-02 | P&E | 0.31 | N/A | 1 |
| multi_hop-dev-02 | Workflow | 0.40 | 0.70 | 0 |
| multi_hop-dev-02 | MA | N/A | N/A | N/A |
| version_boundary-dev-02 | P&E | N/A | N/A | N/A |
| version_boundary-dev-02 | Workflow | 0.33 | 0.667 | 1 |
| version_boundary-dev-02 | MA | 0.33 | 0.667 | 1 |

P&E Goal=1 只来自一条 partial，不能写成三题任务成功率 100%；MA Goal=1 同样只有 2/3 覆盖。Goal 只读 question/final answer/reference，不度量运行完成、原文支持链或恢复。它与 F1、执行状态及 Agent 轨迹诊断不一致时原样保留，不选择其中最高项替代系统可靠性。Faithfulness 仍针对所选来源完整正文，不是 writer 可见片段或逐断言引用正确率。English 问题/reference 与 Chinese 答案、复合 claim 粒度及同模型自评可能影响裁判，当前未人工盲评，不把低分都归咎代码，也不把高 Goal 当成事实无遗漏。

旧开发批次 P&E 为 0 completed / 2 partial / 1 failed，本批为 0 / 1 / 2；Workflow 从 1 / 2 / 0 变为 0 / 3 / 0；MA 从 0 / 1 / 2 变为 0 / 2 / 1。没有完成率提升，P&E 可评分覆盖还从 2/3 变为 1/3；不将两个不同 available-case 均值直接视为独立因果效果，也不将 MA 覆盖改善当成质量提升。

严格校验评分输入 digest、实验身份、裁判身份和 dataset/corpus 后，compare_cli 退出码 0。新批没有 baseline，所有 baseline 配对 n=0，delta/CI 均为 null；不跨身份拼接旧基线制造提升率。

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.compare_cli --input ../tmp/planning-gap-real-answer-20261002/quality_eval.json --scores ../tmp/planning-gap-real-answer-quality-20261002/quality_scores.json --metadata ../tmp/evidence-loop-real-20261002-assets/analysis-card.json --out ../tmp/planning-gap-real-answer-comparison-20261002
```

原始记录：tmp/planning-gap-real-answer-20261002/records.json、quality_eval.json、manifest.json、source_snapshot/；原始评分和逐次裁判请求/返回：tmp/planning-gap-real-answer-quality-20261002/quality_scores.json、attempts.json；覆盖及排除统计：tmp/planning-gap-real-answer-comparison-20261002/comparison.json。评分输入 digest 为 `2014dced266663d33b596c78d8b2741c999d6f9e1e86983a2a679e255cb8f580`。目录均保留，不含导出的 .env；原始请求包含任务和来源正文，公开分享前仍需数据审查。

## 真实轨迹发现

1. 九份初始规划都把“只使用冻结资料”移到 execution_constraints，不再单列“证明遵守过程”的 requirement。但共享指令不能保证语义去重和不扩大任务：P&E 单跳/版本各生成 6 条近义查询，版本还拆成 6 个相近要求；多跳额外加入追踪/跳过机制或兜底等问题。两个 P&E 运行在 evaluator/responder 之前用尽调用，主模式真实完成率仍为 0/3。
2. 单跳 Workflow evaluator 表示可见 thread_id 片段不完整；MA evaluator 返回的 JSON 在 evidence_id 字段中途断开，解析不可用。多跳 P&E 同样 evaluation_unavailable。不能靠放行无支持的 covered 或裁掉门禁解决；本批不对所有 evaluation_unavailable 一概断言同一个截断根因。
3. 多跳 P&E 回答“放到 interrupt 后确保只运行一次”，缺少重试/失败下的条件；Workflow 回答用 None/null 从断点恢复，混淆静态断点与动态 interrupt，并把语言对应写反。原始冻结 interrupts 文档明示动态 interrupt 使用 same thread_id 和 Command(resume=...)，中断节点从头重跑；未改参考答案以迎合这些输出。
4. MA 版本题 follow_up 正确指向缺失 r1，但归一化查询与已派发查询重复，按既有规则拒绝，最终 no_new_assignments。它不是已知 mixed covered/gap 误丢弃问题的重现。本批没有实际合法混合补查任务，因此本轮确定性交集修复有离线真实节点测试，但尚无本批成功补查的实测证明。

## 下一步边界（未实施）

应单独设计最小研究计划、避免近义重复/额外完成条件、降低纯待办消耗、为评估和回答预留运行级调用，再缩小结构化评估输出并核验来源选段。保持事实支持及原始问题约束。当前不把“规划分区正确”包装成系统已可靠可用，也不继续无限提高预算；此文记录首轮失败和下一步依据，而不是完成全部优化的证明。

## 解释边界

这是小规模开发校准，不是独立测试集结论、商业 DeepResearch 对比或生产联网 E2E。三题已参与调试，无重复，Provider 仍非确定性。原 research-v1 共 30 题来源经 Agent 核验，独立人工复核为 0，本批没有新增人工金标或盲评。旧批次至新批次同时包含已先行实施的连接异常分类修复，不能将全部变化归因本轮规划修复。没有新 baseline，不能给出新同条件 baseline 提升率。完成率与有效评分覆盖必须同时呈现，失败、partial、N/A 均保留；裁判及完整来源输入限制沿用原配置。
