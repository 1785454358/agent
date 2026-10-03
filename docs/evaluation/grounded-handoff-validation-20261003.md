# Grounded research handoff 验证（2026-10-03）

## 最终结论

实现与离线回归通过，12次真实研究及两批原始评分均已结束，没有择优重跑或重新评分。原文→候选发现→评估→最后Writer的字面传递审计通过，但整体回答质量没有提高：主模式P&E开发集F1从上一批描述性参照的.563333降为.480000，完成率仍3/3；WF F1上升，MA完成率和分数下降。联网三模式F1均.80，但三次均partial，且存在回答条件泛化或错误版本来源，因此生产联网端到端验收仍未通过。

本轮说明“有出处且能传递”是必要条件，不是“答案完整且任务完成”的充分条件。下一步应优先收紧分支职责、逐项答案义务及版本来源校验，减少循环开销，而不是继续增加代理或单纯扩大预算。以下保留全部不利结果。

## 实验预登记

用户确认的规格：`docs/superpowers/specs/2026-10-03-grounded-research-handoff-design.md`。本轮沿用三模式共享 Harness，不添加代理、检索服务或运行依赖。

改动：授权阅读增加 find/after；实际展示的原文获得分支 n 引用；record_findings 保存有出处的候选发现；候选记录进入 checkpoint、分支上下文和共享评估器。候选主张只有全部出处在当前评估输入完整可见时才出现，不能直接写入全局结论或 coverage。真实联网测评复用生产搜索、抓取和工具门禁，和冻结语料分开标记。

执行 TDD、systematic-debugging 与五轴自审。额外自审检查文件缺失，按技能正文执行；没有独立第二审阅者或人工盲审。现有工作树留样在 `tmp/grounded-handoff-start-20261003`；不提交或覆盖已有无关改动。

冻结语料开发集：3 道已知题 × plan_execute/workflow/multi_agent，各运行一次，Answer 主指标。doubao-seed-2.0-lite、temperature=0、输出4096、Answer 上限2000字符、关闭记忆。每运行40 logical / 80 Provider attempts / 24 Gateway / 12研究迭代 / 360秒；批次360/720。Ragas 独立环境144次 Provider 上限；评分器、金答案和旧语料不改。

联网诊断：1道新题 × 同三模式，各一次；批次120 logical / 240 Provider，评分48 Provider 上限。题目为 Python3.11 TaskGroup/gather 普通子任务异常及 CancelledError 处理，金答案根据 [Python3.11 官方文档](https://docs.python.org/3.11/library/asyncio-task.html#task-groups) 与 [gather 文档](https://docs.python.org/3.11/library/asyncio-task.html#asyncio.gather) 核对并在付费调用前封存。金答案仅用于评分导出；不是独立留出集，不把官方URL注入工具授权，不以本地语料冒充联网。

旧开发结果仅作描述性参照：P&E F1=.563333、Faithfulness=1、Goal=.333333；WF=.536667/1/.333333；MA=.34/1/.666667。本轮不新增 baseline，所以配对 n=0、delta/CI 为 null，不推断显著提升。

输出固定为 `tmp/grounded-handoff-real-answer-20261003`、同名 `-quality`/`-comparison`，以及 `tmp/grounded-handoff-live-answer-20261003`、同名 `-quality`。任何 partial/failed 均保留，不另起目录重跑择优。冻结身份、源码/测试留样和资产哈希由 `tmp/grounded-handoff-preflight.py` 登记到 `tmp/grounded-handoff-freeze-20261003/registration.json`。未配置价格时成本未知，不写为零。

## 执行状态

全量离线回归：1104 passed / 2 deselected（122.08s）；独立 Ragas 环境：34 passed（14.30s）。定向回归经历 reader 2失败→45通过，记录帮助函数8个行为失败→18通过，三模式共享记录循环4失败→31通过，共享材料/上下文20通过，环境及循环20通过，共享规划41通过，最终本地调用计量5通过。新增核心文件的 Ruff 检查和 compileall 通过。现有 dirty 文件的换行警告不表示内容丢失。

付费前预检通过，登记身份：dev `83791b4ab5cce381f2fe60ea6a6600dc5034a6c396e1518260b9f47e0fcfcd5a`；live `9610e6c43819de3e28fee3cf5cde9bae03fa84a2ca26f16e6f74ab062ad271f2`；源码 `a8f9901c9c150fac2c13d8b44cb33a900f31eaf122da83243db3916814491549`，HEAD `65b0551` 加 dirty 源码哈希。两批真实研究与评分均已结束；冻结后未改生产/评分源码，最终只读审计再次验证当前源码与留样一致。

五轴自审：正确性用真实 Gateway/共享循环和跨模式评估测试验证；可读性把记录校验独立成小模块；架构复用既有 DTO/checkpoint，不新建服务；安全保持租户/授权/ACTIVE/版本/哈希/原文定位检查，候选不自动 accepted；性能每次记录缓存来源读取、全部记录/引用/单元有上限，联网搜索离开事件循环，抓取器 finally 关闭。限于代理自审，不声称人工独立审阅。两个附加技能检查文件无法读取，未假称使用。

## 真实执行与逐帧交接审计

两批研究均已结束且没有择优重跑。开发集9次：6 completed / 3 partial / 0 failed；P&E 3/3 completed，WF 2/3，MA 1/3。开发集多跳题 WF/MA 均 iteration_limit；版本题 MA 也 iteration_limit，且回答侧两次 JSON 输出解析失败，最终 response_partial_reason=generation_failed（最终仅列出可追溯资料来源，没有实质答案，完整保留）。联网3次均 partial/iteration_limit，不写成 completed。

`tmp/grounded-handoff-audit.py` 验证当前源码和精确留样，检查实际展示的每条 n 引用、分支命名空间、记录原文坐标/哈希、每次评估输入中的完整候选主张与全部 p 引用，以及最后实际 Writer 输入。12次记录包含50条去重分支候选，最后评估归一化共62条支持；最后 Writer 丢失支持=0，引用证据ID未知=0，artifact_errors=0。结果保存在 `tmp/grounded-handoff-audit-20261003.json`。

这是原文字面传递审计，不是语义蕴含/充分性证明。评估原文有重复时，离线重建采用首个原文位置，只验证文本与来源，不声称这些歧义坐标就是在线坐标。发现记录的实际坐标另按其原始读工具返回严格核对。脚本逐帧处理而非把所有曾可见片段合并成一个假输入；本批每次运行恰有1次评估调用，回答最多2次。不能因此声称多次补查的真实链路已单独检验。

## 开发集最终评分

下表为全部输出（包含partial）的逐题均值，不筛掉低分或降级结果。每模式每指标有效样本3/3，合计27/27 metrics ok，NA=0、评分error=0。completed是运行状态，并非独立语义验收。

| 模式 | completed | Factual F1 | Faithfulness | Goal | 上一批F1（仅描述性参照） |
| --- | --- | --- | --- | --- | --- |
| plan_execute（主指标） | 3/3 | .480000 | 1.000000 | .333333 | .563333 |
| workflow | 2/3 | .610000 | 1.000000 | .333333 | .536667 |
| multi_agent | 1/3 | .250000 | .666667 | .000000 | .340000 |

| 题目 | 模式 | 状态 | Factual F1 | Faithfulness | Goal |
| --- | --- | --- | --- | --- | --- |
| single_hop-dev-01 | plan_execute | completed | .33 | 1 | 0 |
| single_hop-dev-01 | workflow | completed | .67 | 1 | 0 |
| single_hop-dev-01 | multi_agent | completed | .75 | 1 | 0 |
| multi_hop-dev-02 | plan_execute | completed | .25 | 1 | 0 |
| multi_hop-dev-02 | workflow | partial/iteration_limit | .36 | 1 | 0 |
| multi_hop-dev-02 | multi_agent | partial/iteration_limit | .00 | 1 | 0 |
| version_boundary-dev-02 | plan_execute | completed | .86 | 1 | 1 |
| version_boundary-dev-02 | workflow | completed | .80 | 1 | 1 |
| version_boundary-dev-02 | multi_agent | partial/generation_failed | .00 | 0 | 0 |

当前总体F1=.446667，上一批=.480000；completed从8/9降为6/9。不能写成整体优化成功。严格comparison已输出18个比较项，全部baseline配对n=0、delta/CI=null；前后数值不是因果效果估计。均为已知开发题、每题每模式一次、同模型裁判，无独立人工盲审，不证明泛化能力。本轮未新增Report真实评分；Answer和Report不混算。

主模式多跳答案实际只解释节点从头重执行与副作用处理，缺少恢复值传入方式和同一thread_id调用恢复，仍不足以完成用户问的操作流程。版本题则回答了显式RunnableConfig传入ainvoke及显式writer传递，F1=.86。首题回答包含super-step边界和thread_id主键解释，但自动F1仍=.33；这部分分歧需要独立逐主张复核，不能把低分全部归因于代码，也不因代理认为答案合理就改分。多跳答案“副作用移到interrupt之后只运行一次”亦不能泛化为无条件exactly-once保证。

开发研究175 logical / 176 Provider attempts，175次有token usage、1次缺失；已观测输入916611 / 输出62991，完整输入/输出总量为null，不用缺失值填零。开发评分72 Provider / 上限144，输入232672 / 输出75436，全部计量有效。两端成本均null。

| 模式 | Gateway | record_findings | write_todos | 总执行工具调用 |
| --- | --- | --- | --- | --- |
| plan_execute | 23 | 7 | 17 | 47 |
| workflow | 29 | 5 | 17 | 51 |
| multi_agent | 37 | 8 | 24 | 69 |
| 合计 | 89 | 20 | 58 | 167 |

记录与待办是本地执行调用，不消耗Gateway额度，但模型决定、调用、处理它们仍占研究迭代。此批实际58次待办与20次记录说明不能只看Gateway计数判断执行开销；也不能将所有待办调用未经检查都称为空转。

## 联网评分与原文验收

| 模式 | 完成 | Factual F1 | Faithfulness | Goal | 原文/任务验收 |
| --- | --- | --- | --- | --- | --- |
| plan_execute | 0/1 | .80 | .80 | .00 | 未通过：轮数耗尽；将非取消异常泛化为“所有异常” |
| workflow | 0/1 | .80 | 1.00 | 1.00 | 未通过：轮数耗尽，来源实际是Python3.14而非指定3.11 |
| multi_agent | 0/1 | .80 | 1.00 | 1.00 | 未通过：轮数耗尽，来源实际是Python3.14而非指定3.11 |

各指标有效样本均1/1，9/9 metrics ok；不是3题平均，不与开发集混算。三种模式完成真实 search→fetch→read→record→evaluate→Writer→citation 的操作链路，但没有一种同时通过完整产品验收。P&E 回答实际引用3.11.17中文官方正文，另有未选入最终回答的3.14正文；WF/MA只存储并引用3.14.8正文。

关键发现：Python各版本页面的 canonical 链接均指向 `/3/library/asyncio-task.html`，当前证据URL丢失版本路径；审计必须看标题、正文版本和抓取请求，不能仅比较 canonical URL。两个不同版本能有相同URL、不同body/hash/id，脚本用URL+标题区分，不把同URL当成同正文。

P&E Faithfulness 扣分的评分轨迹明确指出“所有异常进ExceptionGroup”遗漏了CancelledError和特殊异常边界，不能靠合法引用解决。Goal 的P&E=0则受Ragas中间 end_state 摘要丢失解释内容影响；WF/MA Goal=1并未检查实际来源版本。保留原始分数，不因代理异议重判或改提示。原文版本验收与自动质量分数分开，以上人工式检查由代理完成，不是独立人工盲审。

联网实际研究82 Provider attempts，输入639552 / 输出28180 tokens，全部计量可用；评分24 attempts、输入57969 / 输出30478，低于48上限。价格未配置，成本null。Gateway/record/todo/总执行调用：P&E 19/2/6/27，WF 15/4/6/25，MA 21/2/2/25；本地调用不消耗Gateway24次额度，但会消耗模型研究迭代。

两批合计354 Provider attempts（研究258、评分96），没有追加研究或重判。总token用量因开发研究1次缺失仍为null；已观测小计输入1846804 / 输出197085，仅为可观测部分，不能当完整账单。

原始联网`report.md`仍继承“offline corpus”标题及旧汇总标签，这是报告模板缺陷，不是实际工具后端。manifest的tools_backend=live_web、corpus_sha256=null，实际轨迹包含Tavily搜索与网络抓取；本报告以这些证据区分联网与冻结语料。旧gold URL完全匹配统计受到canonical路径影响，不能代替来源版本验收。本批冻源后未为修正标签改源码或重跑，后续应独立修复展示。

## 尚未解决的具体问题

1. 分支隔离不够：初始查询虽不同，研究员仍把整体问题/全部requirements纳入自己的todo，造成重复检索。联网各分支均到12轮；有的8次read但未及时record/结束。接下来应收紧“仅完成分配要点”的职责与收尾，非增加agent/服务。
2. 阅读决策效率：模型出现after没有find的非法调用、反复读取宽段和find空命中。新工具能定位原文，但不保证模型选择正确字符串；缺失恢复具体调用方式的开发题仍需检查规划/发现完整性，而不是继续只改Writer材料。
3. 版本范围与来源身份：需要保留版本正确的实际URL/出处信息，并在评估中拒绝用错误版本证明指定版本，不能用统一canonical链接或通用相同事实代替。
4. 语义核验：引用位置/哈希正确只保证“确实读到”；条件、例外和用户询问的操作细节仍可能被模型漏掉。全局覆盖不能只依据笼统requirement或不完整claim判定。
5. 输出稳定性：MA版本题的JSON回答解析与一次纠正均失败，需要单独优化结构化生成/解析契约；不能把fallback当正常回答。
6. 自动评分本身有盲区：Goal是question+final_answer视图，不验证来源版本；多阶段LLM摘要有损且同模型评分有偏差。保留成熟指标，同时需要任务约束、出处版本和独立人工验收，不通过重评分制造高分。

建议下一轮仍复用单一共享研究循环：规划产出明确的答案义务，分支只负责分配到的义务；少做独立待办维护，发现与完成收尾合并；评估逐项核对内容、条件和版本出处，缺口才触发定向补查。保留安全授权与证据校验，不新增协调服务。这个方向是基于失败轨迹的后续建议，本轮没有偷偷修改冻结实现或声称已经验证。

## 原始产物与复现

- 开发研究：[records.json](../../tmp/grounded-handoff-real-answer-20261003/records.json)、[quality_eval.json](../../tmp/grounded-handoff-real-answer-20261003/quality_eval.json)、[manifest.json](../../tmp/grounded-handoff-real-answer-20261003/manifest.json)。
- 开发原始评分：[quality_scores.json](../../tmp/grounded-handoff-real-answer-20261003-quality/quality_scores.json)，同目录identity.json、attempts.json及逐指标缓存保留。最终以quality_scores.json为准，progress.json仍可保留最后一个current检查点，不代表评分还在运行。
- 严格比较：[comparison.md](../../tmp/grounded-handoff-real-answer-20261003-comparison/comparison.md)、[comparison.json](../../tmp/grounded-handoff-real-answer-20261003-comparison/comparison.json)。
- 联网研究：[records.json](../../tmp/grounded-handoff-live-answer-20261003/records.json)、[manifest.json](../../tmp/grounded-handoff-live-answer-20261003/manifest.json)；联网原始评分：[quality_scores.json](../../tmp/grounded-handoff-live-answer-20261003-quality/quality_scores.json)。
- 付费前登记：[registration.json](../../tmp/grounded-handoff-freeze-20261003/registration.json)，同目录source_snapshot/为精确源码及测试留样，不含.env。只有HEAD不足以复现，此处必须同时使用dirty源码身份与留样。
- 只读审计：[grounded-handoff-audit-20261003.json](../../tmp/grounded-handoff-audit-20261003.json)，脚本[grounded-handoff-audit.py](../../tmp/grounded-handoff-audit.py)。[grounded-handoff-summary.py](../../tmp/grounded-handoff-summary.py)汇总原始得分与调用量，均不发API。

真实运行、评分与比较命令保留在执行计划Task8。付费实验已经执行，不应重复运行这些命令来覆盖本批；查看现有产物和只读汇总不消耗模型额度。源码仍在现有dirty工作树中，未把用户已有源码变化整体提交；文档提交不改变上述付费运行身份。
