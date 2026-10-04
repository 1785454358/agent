# 读证据交接与宿主引用解析：验证记录

## 实现与架构边界

用户批准规格并授权必要重构后实施。本轮不是扩大旧 evaluator：新建五个文件承载四个共享职责，分别管理实际读取锚点（DTO/边界两文件）、原文引用单位、评估材料与可见短引用解析；三种策略继续负责各自调度，接入同一证据数据流。没有新框架、服务或依赖。TDD与五轴审查指导了职责拆分、严格契约和兼容性验证，没有改变评分口径。

研究者实际成功读取的片段只记录 evidence_id/version/hash/坐标，跨图与 checkpoint 保留；评估器按已验收 supports、实际读取锚点、旧选择器剩余额度顺序取材。短编号仅对当次最终可见材料有效，模型选择编号，宿主生成逐字引用与来源坐标，不要求模型复制长ID、Markdown或字符位置。编号合法仍不代表语义覆盖，原有事实/冲突门禁继续保留。

每分支最多64锚点、最多8来源/每来源3000字符、最多128单位/每单位500字符。整体JSON再次验算token，掉出可见视图的引用不可解析。新研究契约v3；历史完成v2仍可读取，中途v2不能派发新研究。Writer把验证/省略诊断与事实缺口分开，不能据此声明全文没有信息。记忆准入、权限、模型、预算与评分规则不放宽。

## 离线验证

测试与实现过程详见[实施计划](../superpowers/plans/2026-10-03-evidence-delivery-reference.md)。三模式读取/评估入口与v3消费者有实际失败断言后修复；Task2首轮是模块接口缺失，不伪称为9个语义逻辑RED。后补可见性测试属于实现后验证。脚本夹具迁移到短编号契约，不修改gold、裁判或质量评分。

- 早一轮完整离线：1037 passed / 2 deselected；随后补6项材料可见性测试。
- 定向策略/回答/Harness回归208 passed；最新材料/新draft checkpoint回归10 passed。
- 隔离Ragas评分器34 passed；本次44个Python文件Ruff check与format --check通过。
- 五轴自审：共享职责、原文正确性/安全、版本兼容、有界性能、测试质量；全部源与HEAD在最终回归和真实测试期间冻结。离线脚本通过不等于真实质量提升。

最终冻结完整回归：1043 passed / 2 deselected（116.54秒）；隔离评分器再次34 passed（6.67秒）。

## 真实调用前登记

唯一研究批次 `evidence-delivery-real-answer-20261003`，唯一评分目录 `evidence-delivery-real-answer-quality-20261003`，严格比较目录 `evidence-delivery-real-answer-comparison-20261003`；启动前均不存在。只在最终离线验收和配置核验通过后各跑一次，不按分数重跑。

| 项目 | 固定值 |
| --- | --- |
| 题目 | single_hop-dev-01 / multi_hop-dev-02 / version_boundary-dev-02 |
| 模式 | P&E / Workflow / MA，每题每模式一次，共9个Answer；P&E主指标 |
| 模型 | doubao-seed-2.0-lite，temperature=0，max output4096 |
| 资料 | 7份冻结官方文档，search/fetch使用本地语料；不是生产实时联网端到端 |
| 输出/记忆 | Answer最多2000字符，长时记忆关闭；Report仅离线验收 |
| 单运行上限 | 40逻辑/80 Provider/24工具/12分支轮/360秒 |
| 整批上限 | 360逻辑/720 Provider |
| 评分 | 隔离Ragas0.4.3，相同裁判/scorer/输入限额，最多144 Provider，评分一次 |
| 排除 | 不改gold/裁判/预算，不裁剪失败样本，不新增baseline或调试test split |

HEAD `12a4a79af53b3bea3c5a19cd44a666a77cccc4f6` 不代表全部dirty实现，以manifest文件哈希/留样为受测版本依据。scorer SHA-256仍为 `69144d3c8faeb2f2c77bd68c5139e435baa94f2b19ddbcea2064246c80c17688`。凭据只核验存在，不导出。

启动前规范化数据再次核验：dataset `44da14cc98057d2aa763c0c2117147b71b13167ceeb63ee137aa12c4e0a69dec`，corpus `ffd9e00644024250f508a0d27054c3b96b68e4065b5f0a1ab520ac9648104b8f`；模型、limits、context_allocator、安装包/Python版本、tools/memory backend、模式/重复次数、输出参数逐字段与上一批相同。manifest将覆盖190个源/评分/资产文件；启动后保存源留样和新测试哈希。受控的三道已知dev题、各一次、同模型裁判、无独立人工盲评，不支持显著性、因果或生产可靠性结论。没有新baseline，严格配对n=0/delta/CI=null。

## 真实结果

研究、唯一原生评分和严格比较已全部完成。研究身份 `0a5742e3a27244fb089780e64780217ac7293d7637f64c3f60a1d90cac5a504b`；190份manifest文件逐份复制并核验哈希，六个新增测试独立留样/记录哈希。不是全部1043项测试的完整工作树快照。未导出凭据。

全部9条非空输出，7 completed / 2 partial / 0 failed，artifact_errors=0。研究调用164逻辑/164 Provider、79工具；input tokens681273/output63576，missing usage=0，未配置可核验价格，cost=null。研究CLI退出码1表示含partial，不是整批异常；样本身份、manifest、source_identity再次核验通过，不重跑。

| 题目 | 模式 | 状态 | 逻辑/Provider | 工具 | 原因 |
| --- | --- | --- | --- | --- | --- |
| 单跳 | P&E | completed | 23/23 | 12 | completed |
| 单跳 | Workflow | completed | 11/11 | 4 | completed |
| 单跳 | MA | completed | 18/18 | 9 | completed，保留读锚点省略诊断 |
| 多跳 | P&E | partial | 18/18 | 8 | 研究completed，response_evidence_context_limit |
| 多跳 | Workflow | completed | 17/17 | 8 | completed，responder使用既有一次格式纠正 |
| 多跳 | MA | partial | 22/22 | 15 | iteration_limit，评估覆盖missing |
| 版本 | P&E | completed | 19/19 | 10 | completed，保留读锚点省略诊断 |
| 版本 | Workflow | completed | 20/20 | 6 | completed |
| 版本 | MA | completed | 16/16 | 7 | completed |

只读审计 `tmp/evidence-delivery-audit.py` 解析每次实际模型输入而非历史可见集合：九次评估、105个可见单位、33个模型选择引用、未知编号0；所有单位符合长度限制，与当次可见事件的原文字符坐标、来源URL和body SHA-256逐一一致。该批每运行恰好一次评估，可按事件顺序对应，不把历史集合并成当前映射；多评估批次需另做调用分组。它核验可见引用及原文，不充当独立语义蕴含评审。没有因引用合法自动把missing改为covered。

单跳三模式的实际研究读取、评估输入和已选引用都包含thread_id主键/保存恢复解释；最终答案不再把缺失有效引用说成官方资料不存在。P&E版本题输出回调显式传RunnableConfig与writer显式传参两个核心点。不能据此推广到所有问题。

仍失败的环节已定位：

- 多跳P&E的五条finding在研究评估通过，但writer来源3000字符支持选段没有容纳全部support；实际writer发现列表仅保留前四条，response_evidence_context_limit如实partial。六个唯一引用的原文坐标合并后仅2445字符（48500:50589、50904:51260），不是必要支持本身超出3000。旧贪心逐条添加边距、按quote总长而非合并后的新增成本判断remaining，会挤掉后续必要支持；应先整体保留必要原文再试放上下文边距，而不是调大预算。不是逻辑调用耗尽，不在冻结批次中改门禁掩盖。
- 多跳MA的实际视图以前言、import和错误处理段为主，早期读取锚点占满3000额度；副作用解释不在当次评估输入。模型覆盖missing，分支iteration_limit被保留。Writer后来能从不同回答取材看到幂等说明并生成内容，也不能追认研究覆盖已完成。
- “副作用放在interrupt后只执行一次”的说法来自文档的具体示例语境，不是对外部写入的通用exactly-once保证；仍需独立审查回答是否保留条件，合法原文引用不等于工程承诺成立。

裁判身份/配置与上一批逐字段相同，规范化JSON评分输入SHA-256 `a3b572e4d25f86b181616dfd9b360a8e8ef6bf42c5b4667cb46dcbcbea0ba9bb`（不是带缩进文件的原始字节哈希）。评分/严格compare退出码均0，严格身份、输入、研究manifest、资料与analysis-card核验通过；baseline配对n=0、delta/CI=null。

## 原生质量分数与有效覆盖

以下是全部输出（含partial）的available-case均值，括号为有效题数/尝试题数，不是只取completed的分数。

| 模式 | 完成 | FactualCorrectness F1 | Faithfulness | Agent Goal Accuracy |
| --- | --- | --- | --- | --- |
| P&E（主指标） | 2/3 | 0.493333（3/3） | 1.000000（3/3） | 0.666667（3/3） |
| Workflow | 3/3 | 0.613333（3/3） | 1.000000（2/3） | 0.666667（3/3） |
| MA | 2/3 | 0.530000（3/3） | 1.000000（2/3） | 0.666667（3/3） |

27个指标位：25 ok、2 not_applicable（quality_input_size_limit）、0评分错误。不补零，不裁剪正文重评。两条N/A均为多跳的Faithfulness：Workflow所选来源正文50902+60650=111552字符，MA的完整来源组合也超过既有评分输入限额。FA读取完整selected source body，而非仅writer可见引文，不能将其当作逐条引用的蕴含验收。

| 题目 | 模式 | F1 | Faithfulness | Goal |
| --- | --- | --- | --- | --- |
| 单跳 | P&E | 0.50 | 1.00 | 1 |
| 单跳 | Workflow | 0.75 | 1.00 | 0 |
| 单跳 | MA | 0.50 | 1.00 | 0 |
| 多跳 | P&E | 0.18 | 1.00 | 0 |
| 多跳 | Workflow | 0.29 | N/A | 1 |
| 多跳 | MA | 0.29 | N/A | 1 |
| 版本 | P&E | 0.80 | 1.00 | 1 |
| 版本 | Workflow | 0.80 | 1.00 | 1 |
| 版本 | MA | 0.80 | 1.00 | 1 |

与[上一批同题单次观察](structure-selection-validation-20261003.md)相比：P&E F1 0.286667→0.493333，Faithfulness=1、Goal=0.666667和completed=2/3不变；Workflow F1 0.223333→0.613333、Goal 0.333333→0.666667、completed 0/3→3/3；MA F1 0.390000→0.530000、Goal和completed不变。WF/MA的新FA覆盖2/3而旧批3/3，不能用available均值上涨宣称FA改善。

总completed由4/9变为7/9，研究逻辑/Provider由191变为164、工具由87变为79。这些是已调试dev单批观察，不是因果或节省费用证明。评分68 Provider（全部ok、usage缺失0），input196928/output76816；两条N/A未发该指标调用。总研究+评分232 Provider；与旧批263的差异部分来自评分覆盖不同，不能当公平成本收益。cost仍null。

## 为什么分数仍低：已分离的三类原因

1. **真实链路缺陷仍在。** P&E writer贪心支持预算会丢必要支持；MA按历史读序保留无关前言会挤掉相关事实。原始数据证明需要改数据流，而非只增加轮数或换框架。
2. **答案完整性/边界仍不足。** P&E多跳没有写出同thread_id、Command(resume=...)、resume值作为interrupt返回值等操作细节，也没有清楚区分checkpoint与外部写入的exactly-once边界。不能把低分全部归咎裁判；Faithfulness=1也不表示问题已完整回答。
3. **参考粒度和裁判一致性有限。** F1精度比较短reference，不是完整官方正文。首题P&E把super-step定义并入复合claim，reference没有定义细节，整个claim被判0；反向NLI还因没提per-task pending writes产生缺口。多跳P&E的三个建议/幂等解释实际在官方正文中，但短reference未写全，因此F1精度扣分。该差异应独立校准，不通过迎合gold或重评改分。

首题Goal裁判也不一致：P&E判1时容许未提pending writes；Workflow、MA在同核心目标都已回答的情况下因未提该点判0。已核对保存的原生理由，保留三个原分，不把它们解释为可靠的人类正确率。无独立人工review，human_review=null；后续应校准claim拆分粒度、量词/条件、参考覆盖与二值Goal判定。

## 留样与后续优先级

- 研究manifest：`../../tmp/evidence-delivery-real-answer-20261003/manifest.json`（本地实验留样）、全部研究记录：`../../tmp/evidence-delivery-real-answer-20261003/records.json`（本地实验留样）、源留样：`../../tmp/evidence-delivery-real-answer-20261003/source_snapshot/`（本地实验留样）、新测试哈希：`../../tmp/evidence-delivery-real-answer-20261003/test_snapshot/hashes.json`（本地实验留样）。
- 全部原生评分：`../../tmp/evidence-delivery-real-answer-quality-20261003/quality_scores.json`（本地实验留样）、评分身份：`../../tmp/evidence-delivery-real-answer-quality-20261003/identity.json`（本地实验留样）、实际请求/裁判留样：`../../tmp/evidence-delivery-real-answer-quality-20261003/attempts.json`（本地实验留样）、严格比较：`../../tmp/evidence-delivery-real-answer-comparison-20261003/comparison.md`（本地实验留样）。
- 收尾再次核验190份当前源/快照与manifest、六个新测试/留样、HEAD、原scorer和judge配置不变；未整体提交或覆盖既有dirty工作。

下一步不是继续放大预算，也不需要先迁移整个框架：应整体重构共享的支持预算为“必要原文全局合并→上下文边距”，并让读取保留按固定需求的相关证据取材，而非无条件先到先得。再独立校准裁判、用未见test集与重复运行验证；新行为需单独设计/回归/登记，不回写本批结果。本轮解决了已读证据交接和引用复制，尚未达到生产可靠深度研究Agent的完整验收。
