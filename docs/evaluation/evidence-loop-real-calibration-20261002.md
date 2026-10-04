# 证据闭环：真实模型 API 开发校准

## 运行前登记

2026-10-02 用户明确授权真实 API 调用。采用有界开发批次，不把“额度充足”解释为无限重试；此文件在首个本批付费调用之前登记。

- 主模式：Plan-and-Execute + Answer；Workflow、Multi-Agent、固定流程 baseline 分别报告，不平均成一个正确率。
- 开发题：single_hop-dev-01、multi_hop-dev-02、version_boundary-dev-02，均已用于先前送达诊断；每题每系统重复 1 次，总共 12 个 Answer。
- 未见 test split 不参与调优。题与原文从验证后的 research-v1/dev 投影；7 份冻结官方文档，数据与语料保存在 tmp/evidence-loop-real-20261002-assets/。参考答案/URL 只评分侧使用。
- 原始 benchmark identity：e8dff03c5a52083bd73f3a0f7584130a641df850cc17db877eab11beea31b6de；30 题来源经 Agent 核验，独立人工复核为 0。没有将它称为人工金标。
- 研究模型：doubao-seed-2.0-lite，现有已配置 Provider，temperature=0，最多输出 4096 tokens。不导出凭据。
- Answer 字符上限 2000；每运行最多 40 个逻辑模型调用、80 次 Provider 尝试、24 次工具请求、12 轮分支 Agent、360 秒。每分支循环上限不等于整体运行次数。
- 整批最多 480 个逻辑模型调用、960 次 Provider 尝试。费用尚无可靠价表，不估造价格。
- 长期记忆关闭。冻结本地语料 search/fetch + 真实研究模型，**不是实时联网搜索或网页抓取**；本批 Tavily 调用为 0。
- 执行顺序每题 P&E → Workflow → MA → baseline；不变更生产 API 默认模式。使用独立新输出目录，失败记录保留，不自动创建新目录重试。
- 评分在 .venv-ragas 中运行 Ragas 0.4.3：Faithfulness、FactualCorrectness F1、AgentGoalAccuracy；整批最多 192 次评分 Provider 尝试。默认同一模型裁判，披露自评偏差；不是人工盲评或商业 DeepResearch 对照。
- 不设事后通过线、不删低分、不给缺失/错误评分补零。三道题不足以推断总体质量或显著提升；Report 后续单独验收。

预注册运行 ID：

- evidence-loop-real-answer-20261002-single_hop-dev-01-plan_execute
- evidence-loop-real-answer-20261002-single_hop-dev-01-workflow
- evidence-loop-real-answer-20261002-single_hop-dev-01-multi_agent
- evidence-loop-real-answer-20261002-single_hop-dev-01-baseline
- evidence-loop-real-answer-20261002-multi_hop-dev-02-plan_execute
- evidence-loop-real-answer-20261002-multi_hop-dev-02-workflow
- evidence-loop-real-answer-20261002-multi_hop-dev-02-multi_agent
- evidence-loop-real-answer-20261002-multi_hop-dev-02-baseline
- evidence-loop-real-answer-20261002-version_boundary-dev-02-plan_execute
- evidence-loop-real-answer-20261002-version_boundary-dev-02-workflow
- evidence-loop-real-answer-20261002-version_boundary-dev-02-multi_agent
- evidence-loop-real-answer-20261002-version_boundary-dev-02-baseline

## 复现命令

在 backend 目录执行；会产生真实 API 请求。原运行数据不覆盖，已完成失败同样留样。

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --include-baseline --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 480 --max-batch-provider-attempts 960 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix evidence-loop-real-answer-20261002 --out ../tmp/evidence-loop-real-answer-20261002
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/evidence-loop-real-answer-20261002/quality_eval.json --out ../tmp/evidence-loop-real-answer-quality-20261002 --max-provider-attempts 144 --env-file .env
```

## 结果

12 个冻结资料 Answer 运行已结束，研究 CLI 退出码 1（保留失败样本），实际 300 次 Provider 尝试。P&E 0/3 completed（2 partial、1 failed）；Workflow 1/3 completed（2 partial）；MA 0/3 completed（1 partial、2 failed）；baseline 3/3 completed。没有把有引用的 partial 计为完成。

已观察 input tokens 1,197,897、output tokens 111,543；2 次 Provider 尝试缺少 usage，因此总 Token 不完整，只报告小计，费用为 null。artifact_errors=0。184 份源文件/受控资产已复制到主实验 source_snapshot 并逐份核对哈希，不含 .env。实验身份为 `8fe887607dbe127ed6e4be3bcb1b41e27654c0a4b5a94f37547662e98c85f4d1`。

评分采用 144 次上限，低于最初登记的 192；其余最多 48 次用于下方独立预算诊断。主评分实际 67 次、探针评分实际 14 次，合计 81 次，均完成且退出码 0。主评分 usage 完整：input=194,549、output=80,007；探针评分 input=31,779、output=17,517。费用无可靠价表，保持 null。

### Answer 主指标（修复前冻结实现）

分数 0–1，下表为可评分样本均值，每格同时报告覆盖分母。partial 的非空回答也参与语义评分；failed 无答案为 N/A，不补零或剔除运行状态。每系统 3 题仅重复一次，不能据此推断总体质量。

| 模式 | completed | FactualCorrectness F1 | Faithfulness | AgentGoalAccuracy |
| --- | ---: | ---: | ---: | ---: |
| **P&E（主模式）** | 0/3 | 0.535（2/3） | 1.000（2/3） | 0.500（2/3） |
| Workflow | 1/3 | 0.430（3/3） | 0.782（3/3） | 0.333（3/3） |
| Multi-Agent | 0/3 | 1.000（1/3） | 1.000（1/3） | 1.000（1/3） |
| 固定流程 baseline | 3/3 | 0.290（3/3） | N/A（0/3） | 0.000（3/3） |

MA 的 1.000 仅对应 Python 版本边界题，其余两题无答案，**不是三题正确率 100%**。baseline 的三个 Faithfulness 因完整 selected source body 超过既有 100,000 字符限额为 N/A；未悄悄截断资料来评分。主批总计 36 个指标槽位：24 ok、12 N/A、0 error；N/A 包括 3 个无答案运行 × 3 指标及 baseline 的 3 个超长上下文。Goal 只看问题/最终回答，不衡量跨分支执行或恢复。

Faithfulness 评价 selected_for_outcome 的完整来源正文，**不是 writer 实际可见片段，也不是每个引用与断言逐一对齐的正确率**。该指标可高而答案遗漏问题；答案中英文混合、裁判严格程度和下面的 claim 粒度限制同时披露。

P&E 逐题：single_hop partial 的 F1=0.40 / Faithfulness=1.00 / Goal=0；multi_hop failed，三项 N/A；version_boundary partial 的 F1=0.67 / Faithfulness=1.00 / Goal=1。Workflow 的版本边界题是本批唯一 completed 的 Agent 样本，三项均 1。

严格身份校验后的配对分析保存在 tmp/evidence-loop-real-answer-comparison-20261002/。P&E 与 baseline 的 all-output F1 只有 2 对，均值差 +0.20；completed-only 为 0 对，差异 N/A。MA 只有 1 对可评分；所有 Faithfulness 对比为 0 对，因为 baseline 该项不可评分。**不把这些小样本 available-case 差异写成 Harness 优于基线或显著提升。** 配对排除项和 bootstrap 区间完整保存在 comparison.json。

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.compare_cli --input ../tmp/evidence-loop-real-answer-20261002/quality_eval.json --scores ../tmp/evidence-loop-real-answer-quality-20261002/quality_scores.json --metadata ../tmp/evidence-loop-real-20261002-assets/analysis-card.json --out ../tmp/evidence-loop-real-answer-comparison-20261002
```

原始分数：tmp/evidence-loop-real-answer-quality-20261002/quality_scores.json；每次裁判请求/输出与 usage：同目录 attempts.json。公开展示前仍需检查原始请求内容，不上传凭据或私有任务数据。Report 不在本批实验内，不沿用 Answer 的 completed/质量数字。

### 真实轨迹诊断与后续优化边界

这些诊断来自本批留存轨迹，不把模型裁判分数直接解释成代码根因。

| 题目 | P&E 逻辑调用 / 纯 write_todos 轮 | Workflow | MA |
| --- | ---: | ---: | ---: |
| single_hop-dev-01 | 25 / 10 | 36 / 15 | 40 / 19 |
| multi_hop-dev-02 | 40 / 16 | 30 / 10 | 40 / 17 |
| version_boundary-dev-02 | 21 / 9 | 30 / 13 | 35 / 16 |

纯 write_todos 轮是工具请求非空且仅请求 write_todos 的模型轮数，不能当作网络请求。约三至五成逻辑调用仅更新内部待办，说明预算问题也包含循环效率问题；本次不直接关闭工具或改变策略。

- 规划把“仅使用冻结文档”这类运行约束列为可证据覆盖的 requirement。single_hop P&E 的 r1 被 evaluator 声称 covered 但没有 finding_ids，主机正确将其判 missing；不能取消支持验证来取得 completed。另有补查任务同时包含缺失 r1 与已覆盖 r3，被现有全目标缺口校验丢弃后 no_new_tasks_to_plan。契约整理与补查筛选需单独设计。
- 实际抓取和原文读取成功，不等于回答完整。多跳回答集中在中断重跑和幂等，但遗漏 same thread_id / Command(resume=...)；还有“放在 interrupt 后即确保只执行一次”的过强表达。移到中断后可减少该次恢复重跑的副作用，不等于任何失败/重试下外部写入 exactly-once 保证。
- 结构化评估一次返回大量 finding/support/coverage，在联网冒烟的 2048-token cap 下两次被截断；冻结资料多跳 Workflow 也有 evaluation_unavailable。后续应以具体 finish_reason 区分截断、传输和 schema 失败，不能统一归咎证据不足。
- 新版 LangChain 的 OpenAIConnectionError / OpenAITimeoutError 包装名称没有进入现有暂态白名单。用户仅批准最小分类兼容修复，最多 2 次尝试、预算和计量保持不变；实现完成后另记录，不能回写旧实验状态。

### 裁判结果的解释限制

本批 English 问题/参考与 Chinese 答案由同一模型评分。初查 Ragas FactualCorrectness 的部分 response claims 把多个事实合成一个长复合断言，参考答案缺少其附加解释时整个断言被判不支持；single_hop baseline 虽正确提到 super-step，仍出现 factual F1=0。Goal 裁判也按完整 reference 严格比较；single_hop reference 额外包含题面未直接询问的 pending-writes 边界。这不是单凭本批即可确认的评分器程序缺陷，但说明分数包含 claim 粒度、参考完整性与裁判偏差。

保留原始分数与 prompts/response，不针对低分样本改 gold、评分配置或重评取最好值。后续应对 dev 参考范围和双语 claim 粒度做独立人工复核，再固定新评测版本；原有结果仍单独留存，不能把重评分差异冒称项目质量提升。

主批 Ragas requested-tool Accuracy / F1 已离线运行：12 份任务的 reference_tool_calls 均未定义，两项全为 N/A，coverage=0；不以任意固定工具顺序冒充深度研究任务的标准路径。文件位于 tmp/evidence-loop-real-answer-tool-quality-20261002/。

## 两条高预算诊断（追加执行前登记）

主矩阵中多跳题 P&E / MA 均因 RequestLimitReached 无答案。仅对这两个预先指定失败点做更高资源诊断，不改代码、问题或语料；不删除主记录，不合并为 14 个同条件 benchmark 样本。

新条件：逻辑模型每运行最多 80、Provider 每运行最多 160、工具入口每运行最多 48、Agent 每分支最多 18 轮、模型输出最多 8192 tokens、每运行 600 秒。此为**联合资源探针**，不能把变化归因于单一上限。两个运行的整批逻辑模型上限 160、Provider 上限 320，加主批已用 300，冻结语料研究总上限为 620 次（仍低于本轮 960 次）。独立联网冒烟另按前述最多 80 次模型尝试保留。

预注册 ID：`evidence-loop-real-budget-probe-20261002-multi_hop-dev-02-plan_execute`、`evidence-loop-real-budget-probe-20261002-multi_hop-dev-02-multi_agent`。基线不在该探针内，不能据此作同条件优劣或性能提升声明。记录保存在 `tmp/evidence-loop-real-budget-probe-20261002/`，评分最多 48 次 Provider 尝试、独立身份与目录。

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 80 --max-tool-calls 48 --max-provider-attempts 160 --max-batch-model-calls 160 --max-batch-provider-attempts 320 --agent-iterations 18 --max-output-tokens 8192 --run-timeout 600 --dataset ../tmp/evidence-loop-real-20261002-assets/budget-probe-question.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix evidence-loop-real-budget-probe-20261002 --out ../tmp/evidence-loop-real-budget-probe-20261002
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/evidence-loop-real-budget-probe-20261002/quality_eval.json --out ../tmp/evidence-loop-real-budget-probe-quality-20261002 --max-provider-attempts 48 --env-file .env
```

联合资源探针实际结果（研究 CLI 退出码 1，失败/partial 留样）：

| 模式 | 状态 / 终止原因 | 逻辑模型调用 | Provider 尝试 | 纯 write_todos 轮 | 用时 |
| --- | --- | ---: | ---: | ---: | ---: |
| P&E | partial / no_research_progress | 72 | 72 | 35 | 452.46 秒 |
| MA | partial / max_follow_ups_reached | 61 | 62 | 26 | 229.65 秒 |

两条均有非空引用答案，未达到 completed。P&E 的评估仍不可用；MA 仍缺多个 requirement 支持，且输出中把已完成节点的 pending-writes 行为与中断节点的外部副作用混在一起，不能据此保证外部写入 exactly-once。主矩阵两条无答案变成 partial 是资源诊断现象，不是同条件模型质量或架构提升证据。

探针语义评分：P&E F1=0.29、Faithfulness=1.00、Goal=0；MA F1=0.25、Faithfulness=N/A（完整 selected body 超限）、Goal=0。这仍是多跳题单题资源诊断，未与主矩阵汇总。评分 6 槽位为 5 ok、1 N/A、0 error。

本探针实际 134 次 Provider 尝试，已观察 input=596,238、output=53,923；MA 的 1 次尝试 usage 缺失，探针总 Token 为未知。合并主批研究实际 434 次 Provider 尝试，input 已观察小计 1,794,135、output 已观察小计 165,466，3 次 usage 缺失，费用仍为 null；不计入未经计量的联网冒烟实际请求。

探针实验身份 `c2a31991ba7735342c89be36f0a7856b7c9babe9191322d12a2682449a25c5f4`。其全部 184 个 source_files 与主批 source_snapshot 逐份哈希核对一致（差异 0），共享该快照；两个 manifest 的 Git revision 均为 `606cfbeac8297aa5b7de4f0230a3d61c06fd50e9` 且声明工作区 dirty，不以 HEAD 单独代表代码。

## 独立真实联网冒烟（另登记）

在执行前登记现有 `tests/real/test_real_smoke.py::test_real_workflow_run_returns_cited_answer`：生产 assembly、Workflow、真实 Tavily 与网页抓取，问题“LangGraph 的 checkpoint 机制是什么？”。最多 40 个逻辑模型调用、24 次工具入口、240 秒；SDK 重试关闭、网关最多 2 次模型传输尝试，因此模型 Provider 尝试最多 80 次。工具入口上限不冒称 Tavily 内部重试/HTTP 请求数上限。模型输出最多 2048 tokens，模型传输超时 45 秒。此项不是与上面配对的 Answer 主质量实验，也不证明三模式生产恢复。

使用已验证不存在的专用 pytest basetemp `tmp/evidence-loop-live-workflow-20261002/`，保留 SQLite、来源与运行记录。既有测试按 checkpoint/outcome 一致、实际抓取来源、completed、合法引用验收，不放宽断言。

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/real/test_real_smoke.py -m real -q -s --tb=short --basetemp ../tmp/evidence-loop-live-workflow-20261002
```

联网冒烟实际结果：**1 failed，182.57 秒，退出码 1**。搜索、抓取、read_evidence 成功；应用返回 partial / iteration_limit，35 个步骤、39 次逻辑模型调用、16 次工具入口、3 个返回来源。两次 evaluator 输出均 finish_reason=length、json_invalid；既有 2048-token cap 截断了结构化评估，至少一个研究分支耗尽 12 轮。completed 断言未放宽。工具入口不等于网络请求；此测试未计量真实 Provider 尝试/Token，不填写虚构的实测值。

留样：`tmp/evidence-loop-live-workflow-20261002/result.json` 及专用 basetemp 下 SQLite checkpoint。它证明联网抓取/读取链路连通，但**没有通过完整真实端到端验收**。

## 独立最小异常修复与离线验收

用户确认书面规格后，等研究主批和资源探针结束才修改 `_transient`，仅添加 `OpenAIConnectionError`、`OpenAITimeoutError` 两个名称。现有最多 2 次尝试、预算、SDK 重试配置、退避/超时与错误接口均未变；未改变评分代码或已导出的实验结果。

- TDD RED：真实包装异常离线测试 10 failed、4 passed / 4.92 秒，失败原因是旧代码将其归为 FATAL；不是导入/构造错误。
- GREEN：新旧网关 + 计量测试 25 passed / 3.71 秒；14 个新增用例证明暂态恢复、持续失败两次上限、认证/参数/取消/预算保护、run/batch Provider 尝试限制和缺失 usage 不补零。
- 全后端离线回归 927 passed、2 real deselected / 108.89 秒；隔离评测环境 34 passed / 6.29 秒。网关及新增测试 Ruff check / format --check 通过，不代表全仓旧 lint 问题已清除。
- code-review-and-quality 五轴内联自审无本改动必修阻断项；无新依赖、无 runtime → eval 引用或权限扩张。未进行独立模型复审、打包部署验证，也未新增修复后的付费 E2E 实验。

规格、计划位于 `docs/superpowers/specs/2026-10-02-model-transient-classification-design.md`、`docs/superpowers/plans/2026-10-02-model-transient-classification.md`。本批真实分数评价的是修复前冻结实现，不能把分类兼容修复等同于 planner / 循环 / 评估器问题已解决。

定向提交：规格 `3e62c16`、网关兼容修复 + 新测试 + 计划 `470b02a`；用户已有其他工作区修改和实验数据没有混入。

## 下一轮优化优先级（尚未实施）

1. 分离运行约束与可被来源证明的研究问题，校验 requirement/finding/support 契约；修正补查仅瞄准真正缺口。保留原文支持门禁，不能把 covered 无支持直接放行。
2. 简化待办更新与研究循环，为评估/回答预留运行级调用额度；不能仅放大研究阶段预算。使用主模式 Answer 及三模式一致性的离线回归后再登记真实复测。
3. 减小结构化评估输出规模，保留截断/schema/传输错误的可区分诊断；不要增加无界重试。
4. 独立人工复核 dev 参考范围及 claim 粒度，修订时固定新的评分版本和身份。待开发诊断可靠后，才做未见 test split 正式测评；当前数值不能写成对成熟商业 DeepResearch 的领先结果。
