# 结构保真取材：真实联网恢复验证

## 状态

共享提取、原文选段和阅读预览已实施，离线回归通过。三模式一次性真实研究与评分已完成：主模式 F1 恢复至0.86，但仍 partial，来源约束失败、耗时与搜索增加；完整恢复门槛未通过，不能宣布效率优化成功。本轮不覆盖、重跑或重评分旧结果。

## 实现边界

- 已有 Trafilatura 使用 Markdown，达到原门槛的主提取优先，不再让更长但结构破坏的 BS4 覆盖；BS4 保留段落、行内 API、代码、列表及表格行，迭代遍历防止深层 HTML 递归溢出，排除隐藏注释。
- 原文选择改为完整标识符匹配、实际 API 标题所属内容优先、多目标/既有需求轮转、长度归一排序与同节邻接完整组。不硬编码题目或金答案。
- 默认 query；find 只定位已见原文。长文无命中不前缀兜底，完整组无法放入预览时整组省略并诊断，不从未展示内容建立引用或已读 anchor。
- 短正文能整体放进原预算时保留既有全文读取，strategy=full、found=null，不把词面命中当成语义判断。JSON 超限仍整组省略，显式范围/find 有界窗口兼容保留。
- 不增加 Agent、向量服务、依赖、模型调用、研究轮数或阅读预算；来源身份、授权、hash/version/坐标、安全、恢复、待办与完成门禁不放宽。
- 来源版本执行、fetch/read 合并、规划/Writer 重构和 Goal 评分审计不在本轮范围，相关失败仍计入验收。

## 离线验证和自审

先复现失败再实施提取、标识符/标题排序、完整组预览等行为修改。新增 25 个参数展开后用例，另保留旧安全、授权、恢复与三模式集成回归。只更新本规格废止的无命中前缀/不可分割字符窗口断言。

首次全量回归存在 33 个失败（1147 passed）；澄清短正文全文兼容后全量仍有 7 个失败（1180 passed），根因为隐私/恢复/记忆测试的长正文占位夹具依赖旧前缀兜底。将夹具改成实际问题的分段正文，保留原有 completed、引用上限、完整正文不得泄入状态等断言；没有改成 partial 或删除断言。增量研究夹具还包含其原有 2026 年问题，不用放宽取材兜底解决测试。

最终完整离线：**1187 passed，2 deselected，145.82 秒**；独立 `.venv-ragas`：**34 passed**。变化模块及新增脚本 Ruff、变化模块 compileall、受影响已有跟踪文件 diff whitespace 检查通过。

本会话按 code-review-and-quality 对正确性、复杂度、模块边界、安全和性能自审：三模式仍共用唯一选段器；不增加网络或模型步骤；正文/问题/预览上限沿用原值；隐藏注释和深度 HTML 回归覆盖；评分器未改。该技能引用的两个补充 checklist 文件不存在，使用已读主文件五轴清单，未声称读取缺失文件或独立评审。缺少执行子技能，按 writing-plans 计划与 TDD 在本会话逐项执行。

现场官方 3.11 页面回放使用旧运行实际分支查询、2000 字符原预算，不注入金答案。新选段已包含 TaskGroup 取消与异常聚合、gather 默认异常传播/其他 awaitable 继续、return_exceptions=True，以及取消清理/重新抛出等段落。这里只是取材诊断，不是新的回答评分。

## 一次性真实测试登记

- 数据：`tmp/grounded-handoff-live-assets-20261003/questions.jsonl`，asyncio-live-01，已知诊断题，非 heldout；三模式各一次。
- 新前缀 `structured-retrieval-answer-20261004`；起始副本 `tmp/structured-retrieval-start-20261004`，封存 `tmp/structured-retrieval-freeze-20261004`，不含 `.env`。
- 实验身份 `9a10e8d2d94d03333478ecd93753b4e53e5edeba900a5ca9bf8d5303b84c3226`；源码身份 `18a8daf064613f0ea226d764b5d4835fc15322b4e00ca2699edd56ceb1ca1e9a`。
- 与最近 evidence-first 运行核对除源码/Git/新前缀外控制不变；新检索策略单列 `structure-preserving-entity-section-retrieval-v2`，评分器 hash 未变。
- doubao-seed-2.0-lite、temperature=0、模型输出4096、Answer2000字符、记忆关闭；每分支12轮。
- 每运行40 logical /80 Provider /24 Gateway /360秒；研究批次120 logical /240 Provider。独立 Ragas 0.4.3 一次评分，上限48 Provider；评分错误 N/A，不重评分。
- 主恢复门槛：F1≥0.80 且 completed、指定3.11来源及关键行为合格。未过不扩大付费实验；程序 completed、高 Faithfulness 或单个高 F1 不等于完整验收。

## 真实结果

三模式研究已完成，研究退出码1：主模式与 Workflow 为 partial/iteration_limit，Multi-agent 为 completed。一次评分退出码0，9/9指标有效，评分重试/缺失usage为0。下面的根因来自已落盘真实轨迹与本地重放，不是拟合金答案的检索输入。

| 模式 | 最近F1 → 本轮F1 | 本轮Faithfulness | Goal | 状态 | 严格3.11官方来源 | 秒 | 输入/输出/总token | 搜索尝试代理数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Plan-and-Execute（主） | 0.60 → 0.86 | 0.7273 | 0 | partial / iteration_limit | 否 | 196.36 | 152115 / 11015 / 163130 | 5 |
| Workflow | 0.83 → 0.80 | 0.8000 | 0 | partial / iteration_limit | 否 | 153.00 | 118246 / 12250 / 130496 | 2 |
| Multi-agent | 0.91 → 0.67 | 0.8750 | 0 | completed | 否 | 80.32 | 88929 / 7453 / 96382 | 4 |

completed 1/3，严格来源0/3，完整验收0/3。主模式引用了3.11官方页、3.12a0镜像与3.13官方页；Workflow引用3.11与默认新版页；Multi-agent引用3.11 task页与默认新版 exceptions页。都不能宣称“仅依据Python 3.11官方文档”。

本会话逐条核对实际答案：三模式均写出TaskGroup取消剩余任务及异常聚合、gather默认首异常立即传播/其他子任务继续、取消后的清理与重新抛出、不应吞掉取消的基本原因；三模式均未写 return_exceptions=True，主模式和MA还漏 uncancel 例外，MA未明确 timeout。主模式“必须重新引发”缺少通常/例外限定。基本四项写对不是全部条件/例外和版本验收合格；这是本会话审阅，不称独立人工评审。

与最近主模式相比：F1 +0.26，但耗时155.33→196.36秒（+26.4%）、总token147763→163130（+10.4%）、搜索代理数2→5。相对旧0.80参照总token减少25.4%，但时间增加50.5%，搜索3→5；旧/新均未完整合格，没有成功成本配对。MA时间/token降低同时F1下降，不计为用户要求的质量不降效率收益。本轮不扩大付费实验。

研究计量：75次Provider尝试，输入359290、输出30718、总390008，三模式时长合计429.68秒；Gateway46次（search11、fetch10、read25），工具重试0，fetch两次缓存，其中主模式另有授权拒绝，不能将fetch请求数当实际HTTP成功抓取数。搜索11为无缓存/重放/工具重试下的供应商尝试代理数，不是发票/credits。评分独立计量：24次Provider尝试（上限48），输入69547、输出34935、总104482，24次usage完整，费用未知。

运行前后源码/测试及封存hash、评分器及judge身份已核对一致。复用上轮字面审计只替换产物路径：3条运行、12个候选记录、最后评估归一化支持22条、Writer遗漏0、artifact错误0；另核对14条record_findings原文支持均来自该分支实际已展示范围。这是原文/可见性审计，不是语义证明，不保证Writer没有新增或遗漏未被接受的答案要点。

### 关键失败已精确重放

主模式首次评估 sequence=16 前，三个分支完成了4次读取，其中3.11页有两次 find 和一次 query；query 原文确实包含 gather 的 return_exceptions 和“不取消其他任务”等核心行为。全局评估输入却没有这段原文，r2 被判 missing 并触发补查。

`tmp/structured-retrieval-anchor-replay.py` 用实际问题、固定 requirements 和实际已读坐标重放 `select_read_passages`，选中 `[1223,2223]` 与 `[4140,6140]`，恰为3000原文字符，与首次评估 s1 的所有可见片段拼接**逐字相同**。较大的泛化 find 窗口挤掉 gather 关键组，产生 read_anchor_omitted。最后评估 sequence=30 仍不含 return_exceptions 原文，而补查分支已再次读到相应条件。

根因不是再多一点研究轮数：阅读使用了新结构选段，但评估侧 `tools/evidence_units.py::select_read_passages` 对已读范围仍另做旧式通用词累加排序；有已读范围时不会调用新共享 query 选段器。本轮未将该重复排序一起替换，这是端到端修复范围不够完整。后续应统一两处取材规则，在现有授权已读范围内按需求保留关键完整组，不新增 Agent/排序服务、不扩大预算，也不回退候选记录充当语义证明。

主模式分支轮数6/3/6，补查12轮；8次read中6次find、1次query、1次full。find没有空命中，但多次先命中例子或普通Task相关窗口；补查中一次 fetch 因 url_not_authorized 被拒绝，权限未放宽。Workflow分支12/7轮；Multi-agent6/5/6轮。仅加提示不保证模型总按 query 走，定位导航仍需在后续独立替换中处理。

### 主模式已完成的评分解释

主模式原始F1=0.86（最近0.60）、Faithfulness=8/11≈0.7273、Goal=0。Faithfulness 的8条技术陈述全部 verdict=1；3条文档 URL 陈述因评分 context 未包含 URL 被判0。它不代表27%的技术陈述错误；这是评分输入/陈述分解需要独立审计的信号，不擅自删 URL claim 或重评分。来源确实混入3.12a0镜像与3.13官方页面，严格仅依据3.11官方要求仍失败，不用评分信号解释掩盖版本错误。

F1回答拆为6条claim均被金答案支持；金答案拆为4条，其中 return_exceptions=True 和 uncancel 两条复合陈述判未覆盖。缺漏仍存在，claim分解粒度也不同于历史轮，因此0.86不能单独证明条件和例外已完整覆盖。Goal=0及程序partial原样保留。

MA原F1=0.67：回答5条claim中4条技术claim通过、出处claim不被金答案支持；金答案4条复合claim中3条判未覆盖，涉及return_exceptions=True、timeout与uncancel。TP=4/FP=1/FN=3，未删掉出处claim或改金答案。Goal均为0，保持原始评分；已知泛化end_state提取需另审，但不能用它掩盖partial/版本错误。

留样：`tmp/structured-retrieval-freeze-20261004/registration.json`、`tmp/structured-retrieval-answer-20261004/records.json`、`tmp/structured-retrieval-answer-20261004-quality/quality_scores.json`及`attempts.json`、`tmp/structured-retrieval-summary-20261004.json`、`tmp/structured-retrieval-audit-20261004.json`。本地根因重放脚本为`tmp/structured-retrieval-anchor-replay.py`，无需真实API。

历史主模式参照：grounded-handoff F1 0.80、130.45秒、218630 总token、搜索代理数3；最近 evidence-first F1 0.60、155.33秒、147763 总token、搜索代理数2。历史臂均未完整合格，不能据此声称成功配对的省时、省token。

## 限制

同一已知题、每模式一次、同模型评分、实时网页可能变化；不是多题统计结论或独立人工验收。不改金答案，不择优重跑，不在正文中掩盖失败。
