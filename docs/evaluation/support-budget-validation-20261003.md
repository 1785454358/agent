# Global Support Budget 实证记录（2026-10-03）

## 预登记：付费调用前

用户批准共享预算规格，并要求以真实 API 验证为重点。只改 `tools/evidence_views.py` 的必要原文/可选上下文分配；评分器、模型、提示、gold、证据门禁和预算不改。保留全部失败、partial 与 NA，不重跑挑分、不补评分、不新增 baseline。

冻结 HEAD `fb4cc480a8db0dbfa98813e1115662b0e53144b5`，工作树脏；以 190 文件哈希及完整源留样为准，不以 HEAD 单独冒充可复现版本。实验身份 `209ba335bec4e35372b6dde369c9242d2478918fe570740c482a3789c5d94bac`。登记文件 `tmp/support-budget-registration-20261003.json`。

与上批逐字段核验：同三道已知 dev 题、同七篇冻结官方资料、三模式各一次（9 个 Answer）、2000 字符回答上限、doubao-seed-2.0-lite、temperature 0、4096 输出 token。每运行 40 逻辑调用/80 Provider/24 工具/12 分支轮/360 秒，整批 360 逻辑/720 Provider；allocator 128000/4096/2048；长期记忆关闭。

数据归一化 SHA256 `44da14cc98057d2aa763c0c2117147b71b13167ceeb63ee137aa12c4e0a69dec`；语料 `ffd9e00644024250f508a0d27054c3b96b68e4065b5f0a1ab520ac9648104b8f`。190 文件中仅 evidence_views.py 改变。评分器 SHA256 `69144d3c8faeb2f2c77bd68c5139e435baa94f2b19ddbcea2064246c80c17688` 未变。独立环境 Ragas 0.4.3、openai 3.3.0、instructor 1.17.0、同模型裁判、temperature 0、2048 输出 token、SDK 重试 0、instructor 尝试 1，最多 144 Provider。

研究一次、原生评分一次、strict compare 一次，命令见 `docs/superpowers/plans/2026-10-03-global-support-budget.md`。唯一输出为 tmp/support-budget-real-answer-20261003 及其 quality/comparison 目录，预检确认三者不存在。无新 baseline：配对 n=0，delta/CI=null。

## 离线验证与五轴自审

- TDD：先修正测试夹具的 r1..r6 编号，再观察旧算法 17 个实际断言失败/11 通过；包含三个真实策略评估入口、v2/v3 Answer Writer，非导入错误。实现后新增 28 项全部通过；Report 原实现已通过，作为兼容回归而非虚报修复效果。
- 完整后端：1071 passed、2 real deselected，114.41 秒。独立 Ragas 环境：34 passed、6.79 秒。Ruff 检查通过；格式化不改变其他生产文件，没有安装生产依赖。
- 旧真实多跳 P&E 离线回放：8 个有效支持/6 个唯一单位，必要并集 2445 字符；新范围 48380:50709、50784:51380（含上下文 2925 字符），全部完整可见，包括原先丢失的 finding-5。仅证明分配修复，不是新 API 质量得分。
- 正确性：先封存必要并集，真正超限才按稳定顺序选择完整引用；合并增量计费，严格正整数字额、重复/重叠/相邻/正文边界已测。
- 可读性/架构：一个共享入口、两阶段确定性算法、小型并集长度函数；不为三模式复制分配器或新增服务。
- 安全：沿用来源/版本/hash/坐标/逐字检查及最终可见性门禁；model_copy 非法对象、真超限、整体 token 丢失仍不能假装完成；无新依赖或密钥输出。
- 性能：每范围最多约 7 次二分合并检查，支持集受现有领域规模限制；未引入模型调用或整篇反复语义评分。自审无阻断问题；非独立模型审查。

## 真实结果

已完成研究一次、原生评分一次、strict compare 一次，未重跑或重判。研究 CLI 返回 1 是因为保留了一条 partial；评分与比较均返回 0。源与留样重新校验全部一致，运行身份与预登记一致。

9 条均有非空回答：8 completed、1 partial、0 failed，artifact_errors=0。主模式 P&E 为 3/3 completed；Workflow 多跳题达到 iteration_limit，保留 partial；MA 为 3/3 completed。`answered` 在系统报告中是完成状态相关指标，不能把 Workflow partial 的非空回答改算作完成。

| 模式 | completed | Factual F1 | Faithfulness | Goal Accuracy | 每指标有效覆盖 |
| --- | ---: | ---: | ---: | ---: | --- |
| P&E（主指标） | 3/3 | 0.563333 | 1.000000 | 0.333333 | 3/3 |
| Workflow | 2/3 | 0.536667 | 1.000000 | 0.333333 | 3/3 |
| Multi-Agent | 3/3 | 0.340000 | 1.000000 | 0.666667 | 3/3 |

以上是全部输出均值，包含 partial，非只筛 completed 的均值。原生 27/27 指标 status=ok；NA=0、评分 error=0；未裁剪正文或补 NA。

| 题目 | 模式 | 状态 | F1 | Faithfulness | Goal | 逻辑/Provider | 工具 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| single_hop-dev-01 | P&E | completed | 0.50 | 1.00 | 0 | 11/11 | 5 |
| single_hop-dev-01 | Workflow | completed | 0.50 | 1.00 | 0 | 17/17 | 8 |
| single_hop-dev-01 | Multi-Agent | completed | 0.00 | 1.00 | 1 | 20/20 | 10 |
| multi_hop-dev-02 | P&E | completed | 0.33 | 1.00 | 0 | 15/15 | 6 |
| multi_hop-dev-02 | Workflow | partial / iteration_limit | 0.25 | 1.00 | 0 | 21/21 | 13 |
| multi_hop-dev-02 | Multi-Agent | completed | 0.22 | 1.00 | 0 | 15/15 | 6 |
| version_boundary-dev-02 | P&E | completed | 0.86 | 1.00 | 1 | 17/17 | 8 |
| version_boundary-dev-02 | Workflow | completed | 0.86 | 1.00 | 1 | 16/16 | 7 |
| version_boundary-dev-02 | Multi-Agent | completed | 0.80 | 1.00 | 1 | 18/18 | 9 |

### 调用与完整性

- 研究：150 逻辑调用、150 Provider、72 工具；输入 606446 / 输出 58317 tokens；150/150 usage 有记录。运行耗时合计 806508.14 ms，非生产延迟 SLA。
- 评分：72 Provider / 上限 144；输入 234063 / 输出 81818 tokens；72/72 usage 有记录。合计真实 Provider 222 次、输入 840509 / 输出 140135 tokens。两端 cost=null，未配置价格，不能把它解释为免费或已计算账单。
- 评分归一化输入 SHA256 `e9ad197b99258d4fc0bb44299f4f2920e1a43d45a9469c97e943900da902ad7c` 与实际 identity.json 一致；这是归一化 JSON digest，不是原始文件字节哈希。评分结果的 experiment_identity 与研究一致，实际 judge 字典与上批完全一致。
- 9 条各一次 evaluator 调用，共 84 个实际评估原文单位，32 个模型选择短引用；全部可映射当前可见 ref、1..500 字符、正确原文坐标/来源 URL/content hash，无未知 ref。坐标/hash 验证按每条单帧逐一映射，不以多个阶段的可见范围并集冒充最终输入。
- 对实际最后一次 Writer 输入及对应可见事件核验：32 个被接受的支持都完整可见、逐字原文及 claim 均在实际 prompt；全部 cited_evidence_ids 属于当前 evidence_ids。Workflow 多跳无接受支持（0 条），其 partial 未被空集的可见性检查洗成成功。本批 response_evidence_context_limit=0，Writer 均一次生成。
- 引用原文可见/ID 有效不等于语义蕴含、操作完整或成功恢复；Faithfulness=1 也不能替代 Goal/F1 或独立人工复核。

### 与上一批的描述性对照

上批 evidence-delivery：completed 7/9；P&E F1 0.493333、Workflow 0.613333、MA 0.530000。新批 completed 8/9，P&E F1 0.563333，另两模式 F1 降低；跨模式全部 9 条总体 F1 从约 0.545556 降到 0.480000。P&E/Workflow Goal 从各 0.666667 降为各 0.333333，MA Goal 维持 0.666667。不能概括为“整体质量提高”。

上批 FA 有效 7/9（两条输入超限 NA），本批 9/9，但输入限额/评分器未变；实际取材和生成轨迹不同。每条仅一次、无新 baseline。strict compare 18 个比较项均 baseline 配对 n=0、delta/CI=null；这些上批数值对照不是严格新旧配对效应估计。

本批九条都只有一次 evaluator；没有证据说明首轮取材或模型推理差异由支持预算修复导致。修复的直接机制证据是通用回归测试和旧真实支持回放，不是新批 completed 数或 F1 单点变化。

## 剩余问题与后续优先级（本批不改动）

1. **资料存在，关键内容未进入评估材料。** 三模式多跳原始来源都有 `Command(resume=...)`，实际评估视图均没有该操作示例，最终答案也没有具体恢复调用。P&E/MA 主要保留“节点重执行”和副作用建议；本次修复只保证已接受 supports 不被上下文挤掉，不能把尚未选中的事实自动补齐。下一轮优先独立设计面向需求的读片段选择，而非继续增加总调用预算。
2. **covered 仍可能是过粗判定。** P&E/MA 把宽泛的“恢复流程”标 covered，却没有提交恢复指令、恢复值以及完整线程定位流程；Workflow 则将相关需求判 missing，并到 iteration_limit。需要让答案义务及完成判据能检测这些遗漏，不能只检查 Finding 有引用；也不能针对这道已知 dev 硬编码关键词放宽门禁。
3. **高 Faithfulness 不能证明高质量。** 三条多跳 Faithfulness 都是 1、Goal 都是 0；存在有出处但不完整的答案。“将副作用移到 interrupt 后”也不能泛化成无条件 exactly-once 保证。需要继续保留不确定性及适用条件。
4. **裁判需校准而非挑分。** MA 首题 Goal=1、F1=0，答案实际上包含超步边界及 thread_id 解释；自动指标存在明显分歧，不能未经独立人工复核就断言零分全是项目错或全是裁判错。当前 human_review=null，缓存只保存聚合结果，尚不足以定位每条 claim 的误判。后续可单独登记多裁判/盲审及 claim 级诊断，但不能重判本批来替换不利结果。

结论：共享必要支持预算修复通过；真实 API 链路已完整测量，但项目整体高质量、三模式可靠性和生产联网端到端尚未验收通过。

## 原始产物与复现

- `tmp/support-budget-real-answer-20261003/records.json`：全部 9 条答案、来源、状态及轨迹；`quality_eval.json`：评分输入；`source_snapshot/` 与 `test_snapshot/`：冻源及新测试留样；`registration.json`：完整实验身份。
- 同目录 `visibility-audit.json`、`writer-support-audit.json`、`final-audit.json`：可见原文及最终 Writer 核验。只读审计脚本 `tmp/evidence-delivery-audit.py`、`tmp/support-budget-final-audit.py`，不发 API、不重判。
- `tmp/support-budget-real-answer-quality-20261003/quality_scores.json`、`identity.json`、`attempts.json`：原生得分、裁判身份及调用用量。
- `tmp/support-budget-real-answer-comparison-20261003/comparison.json` / `comparison.md`：严格比较及覆盖。没有新 baseline，禁止据此写对 baseline 的提升百分比。

## 解释边界

这是真实模型/评分 API + 冻结本地资料，不是生产联网搜索抓取端到端测试。仅 3 道已调试 dev、各一次、同模型裁判、无独立人工复核；与上批只能描述性对照，不能证明因果提升或泛化可靠性。评分输入限额原样保留，NA 不按满分或零分填充。预算分配修复不保证补齐恢复细节，不处理 MA 无关前言取材或裁判一致性。
