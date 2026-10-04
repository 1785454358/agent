# 最小覆盖规划：实现与同预算校准

## 实现与验证边界

用户审阅 2026-10-03 规格并回复“开始”。仅修改共享 planning_instruction 文本：初始优先 1–min(3, limit) 条最少互补查询，一条查询可覆盖多个答案要点；合并近义事实，不把搜索、提取、核验已有结论和汇总写作各派为初始研究任务。保留真正事实核查、显式子问题与必要事实边界，不新增验收要求。

不是硬裁三条，P&E / MA / Workflow 默认上限 6 / 5 / 3、requirements 1–6 不变。所有解析、封存、补查、证据校验、checkpoint、权限、预算、模型、重试及评分保持原样。没有宿主语义去重，也没有实现回答阶段预算预留。

新增 21 项真实规划节点模型输入/保护回归。最初夹具误用 a–d requirement ID，与现有 r1–r6 契约冲突；仅修正夹具，未改生产接口。干净 RED 为 9 failed / 12 passed；生产提示更新后定向回归 191 passed，隔离 Ragas 回归 34 passed，唯一生产文件和新测试 Ruff check / format --check 通过。冻结完整回归 987 passed / 2 deselected（138.29 秒）。

按 code-review-and-quality 五轴自审：正确性保留合法四问题及坏规划回退；安全不扩权限；维护性复用单一入口；测试调用真实三模式节点而非源码检查；兼容性保留原字段与 checkpoint。提示字句测试只证明契约送达，不证明模型语义行为或调用收益。对照上批 manifest，185 个受测文件中仅 planning.py 哈希变化；既有 dirty 工作保留，未整体提交。

## 付费前登记

本节在启动真实调用前登记。批次只跑一次，不追加高分重跑。

| 项目 | 固定值 |
| --- | --- |
| 批次 | minimal-plan-real-answer-20261003 |
| 题目 | single_hop-dev-01 / multi_hop-dev-02 / version_boundary-dev-02 |
| 模式 | plan_execute / workflow / multi_agent，每题每模式一次，共 9 条 |
| 模型与资料 | doubao-seed-2.0-lite，temperature=0，最多 4096 输出 token；7 篇冻结官方文档，本地 search/fetch |
| 输出 | Answer 最多 2000 字符，长时记忆关闭；不测 Report |
| 每运行上限 | 40 逻辑调用 / 80 Provider 尝试 / 24 工具入口 / 12 分支轮 / 360 秒 |
| 整批上限 | 360 逻辑调用 / 720 Provider 尝试 |
| 评分 | 隔离 Ragas 0.4.3，旧配置/模型/标准，最多 144 Provider 尝试，只评分一次 |
| 排除 | 不改 gold，不扩预算，不新跑 baseline / test split，不给 N/A 临时裁剪源正文 |

规范化 dataset SHA-256 为 `44da14cc98057d2aa763c0c2117147b71b13167ceeb63ee137aa12c4e0a69dec`，corpus 为 `ffd9e00644024250f508a0d27054c3b96b68e4065b5f0a1ab520ac9648104b8f`，已按 load_questions/load_corpus DTO 内容校验。三题来自已有开发集，不是新建独立测试集；gold 只在评分侧使用。启动前三个登记目录均不存在。

命令与步骤见 [实施计划](../superpowers/plans/2026-10-03-minimal-coverage-planning.md)。HEAD 冻结为 `f96a6aaac1ca47905b3da0cced6587a000ed8afc`；工作树实现以 manifest 哈希及 source_snapshot 为准，不以 HEAD 冒充完整代码。全量回归和真实批次期间不修改源码/HEAD。

研究身份 `94eae95ac3a06d2668c2871a39de5a6828d945f8886d575409a46aa955617b3d`。启动后 185 个 manifest 文件已保存到批次 source_snapshot 并逐份 SHA-256 校验；不含凭据。新测试另存 SHA-256 为 `1f55612a6a39dbfb4ec8398cecfc2f7ab8a7a3b44c01a7e22ba3012a77154736`。这 185 份文件不是完整测试工作树，不能冒充包含全部 987 项测试的快照。

## 真实结果

研究结束，CLI 退出码 1：4 completed / 5 partial / 0 failed，9 条均有非空回答，answered=4（无 response_partial_reason），不等于有答案条数。未重跑、未追加调用预算。真实模型 + 冻结本地资料不是生产联网端到端测试。三题 dev、单次重复、同模型裁判、无独立人工盲评；与旧批差异只能作开发诊断，不能作因果或总体质量结论。

研究共 183 逻辑调用 = 183 Provider 尝试、81 个工具入口，input=708,239 / output=82,053，missing usage=0、artifact_errors=0、Provider API errors=0。费用没有可靠价表，为 null。实际调用上限并非费用预测。

| 题目 | 模式 | 状态 / 原因 | 逻辑 / Provider | 工具入口 | 纯待办轮 | 实际分支 | 秒 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| single_hop-dev-01 | P&E | partial / no_research_progress | 33 / 33 | 13 | 12 | 3 | 215.40 |
| single_hop-dev-01 | Workflow | partial / insufficient_evidence | 20 / 20 | 9 | 6 | 2 | 116.56 |
| single_hop-dev-01 | MA | partial / no_research_progress | 23 / 23 | 10 | 5 | 3 | 130.73 |
| multi_hop-dev-02 | P&E | completed | 14 / 14 | 6 | 3 | 2 | 107.01 |
| multi_hop-dev-02 | Workflow | partial / insufficient_evidence | 22 / 22 | 9 | 8 | 2 | 144.35 |
| multi_hop-dev-02 | MA | completed | 16 / 16 | 6 | 5 | 2 | 83.54 |
| version_boundary-dev-02 | P&E | partial / max_replans_reached | 20 / 20 | 10 | 4 | 2 | 119.54 |
| version_boundary-dev-02 | Workflow | completed | 15 / 15 | 6 | 4 | 2 | 62.60 |
| version_boundary-dev-02 | MA | completed | 20 / 20 | 12 | 3 | 2 | 85.90 |

### 规划与执行阶段

每条初始规划均为 2 查询 / 2 requirements，三道问题都保留了两项答案要点。实测不是宿主硬裁剪；四个合法独立问题仍由离线保护测试验证可保留。语义保留情况只针对这三题检查，不能推广所有任务。

| 题目 | P&E 初始查询/要点 上批→本批 | Workflow 上批→本批 | MA 上批→本批 |
| --- | --- | --- | --- |
| 单跳 | 2/2→2/2 | 2/2→2/2 | 2/2→2/2 |
| 多跳 | 3/3→2/2 | 3/3→2/2 | 5/3→2/2 |
| 版本边界 | 6/4→2/2 | 2/2→2/2 | 5/4→2/2 |

本批 9 条都进入 evaluator 和 responder。P&E 单跳为 planner 1 / researcher 28 / evaluator 2 / replanner 1 / responder 1；多跳 1 / 11 / 1 / 0 / 1；版本 1 / 16 / 1 / 1 / 1。MA 对应 supervisor/researcher/evaluator/follow_up/responder：单跳 1/18/2/1/1，多跳 1/13/1/0/1，版本 1/17/1/0/1。Workflow planner/evaluator/responder 各 1，researcher 分别 17/19/12。

上一批三条失败都是 planner/supervisor 1 + researcher 39，没有进入评估和回答。本轮减少了初始任务，并观察到全部进入后续阶段；这不是实现了硬性阶段预算预留。实际分支按不同 researcher 标签计数，含补查、不表示全部成功，不能与初始查询数混用。

### 与上一批的开发对照

| 模式 | completed 上批→本批 | 非空答案 上批→本批 | 逻辑调用 上批→本批 | 纯待办轮 上批→本批 | 实际分支 上批→本批 |
| --- | ---: | ---: | ---: | ---: | ---: |
| P&E（主模式） | 1→1 / 3 | 2→3 / 3 | 96→67 | 22→19 | 11→7 |
| Workflow | 2→1 / 3 | 3→3 / 3 | 54→57 | 12→18 | 7→6 |
| MA | 0→2 / 3 | 1→3 / 3 | 97→59 | 33→13 | 12→7 |

整体 completed 3→4，failed 3→0，非空答案 6→9。模型调用 247→183（少 64 次，25.9%），工具入口 131→81；纯待办轮 67→50，比例 27.1%→27.3%，不能宣称待办占比继续改善。P&E 单跳从 completed 变为 partial；多跳从 partial 变为 completed；版本从 failed 变为 partial。Workflow 完成率下降且调用增加，必须保留，不得只呈现 MA 改善。

模型、limits、context_allocator、数据哈希、tools/memory backend、输出、重复次数和安装包版本与上批相同，逐字段核对通过。研究结束 source_identity 差异为 0。

### 待优化问题（诊断，不是本轮修复）

1. 单跳三模式都缺 thread_id 的有效支持：评估器看到的关键段落不完整；P&E/Workflow 拼接了含省略号的 quote，原文支持门禁拒绝。不得把“当前选段没看见”写成“官方资料没有”。P&E/MA 补查后无新进展。
2. P&E 版本题已保留两项问题并生成两项 finding。回调传播的完整段落已经送达，quote 长 494（未超过 500），passage ID 正确，但模型将原文句间换行改为空格，导致逐字子串查找失败；另一个 112 字符的 writer quote 则匹配通过。重规划提出同一查询，被既有去重过滤，状态 max_replans_reached，gaps 含 no_new_tasks_to_plan。不能把这个状态名解读为确实进行了多轮额外研究，也不能归因于缺资料或预算耗尽。后续应设计可靠 quote 构造，不临时放宽门禁。
3. Workflow 多跳 r2 未通过支持校验，却在回答中把资料说成只讲预防、不讲处理，同时给出幂等建议；回答与缺口说明需更精确。
4. P&E/MA 多跳回答含“中断后只执行一次”较强表述；宿主原文坐标与覆盖门禁不是逐主张语义蕴含或生产 exactly-once 保证。runtime completed 不等于事实完整或全部主张可靠。

本轮不混改选段、quote 结构、补查或阶段预算，保留差异的可追踪性。以上应作为下轮独立设计依据。

## 原生评分

隔离 Ragas 0.4.3 评分完成，退出码 0，只评分一次：70 / 144 Provider 尝试，input=213,405 / output=74,971，missing usage=0、费用 null。研究加评分共 253 次尝试，input=921,644 / output=157,024。裁判配置逐字段与上批相同，scorer SHA-256 为 `69144d3c8faeb2f2c77bd68c5139e435baa94f2b19ddbcea2064246c80c17688`；评分输入 SHA-256 为 `e5ce338e567cee16daf414411673b6490f7117f3ab72101f167f35955d44574c`。

27 个指标槽位：26 ok / 1 not_applicable / 0 error。唯一 N/A 是 Workflow 多跳的 Faithfulness，完整 selected source body 超过既有 100,000 字符限额；未裁剪、未补零、未重评。严格 compare 身份检查通过，退出码 0；没有新增 baseline，所有 baseline 配对 n=0、delta / CI=null，不是有统计显著性的产品对照。

| 模式 | completed | partial / failed | 事实 F1（有效/全部） | Faithfulness（有效/全部） | Goal（有效/全部） |
| --- | ---: | ---: | ---: | ---: | ---: |
| P&E（主模式） | 1/3 | 2 / 0 | 0.377（3/3） | 0.783（3/3） | 0.000（3/3） |
| Workflow | 1/3 | 2 / 0 | 0.307（3/3） | 0.833（2/3） | 0.000（3/3） |
| MA | 2/3 | 1 / 0 | 0.370（3/3） | 0.833（3/3） | 0.333（3/3） |

| 题目 | 模式 | F1 | Faithfulness | Goal |
| --- | --- | ---: | ---: | ---: |
| 单跳 | P&E | 0.40 | 0.75 | 0 |
| 单跳 | Workflow | 0 | 0.667 | 0 |
| 单跳 | MA | 0 | 0.50 | 0 |
| 多跳 | P&E | 0.40 | 1 | 0 |
| 多跳 | Workflow | 0.25 | N/A | 0 |
| 多跳 | MA | 0.44 | 1 | 0 |
| 版本 | P&E | 0.33 | 0.60 | 0 |
| 版本 | Workflow | 0.67 | 1 | 0 |
| 版本 | MA | 0.67 | 1 | 1 |

以上为 available-case 均值与覆盖，不是所有题正确率。上批 P&E F1 0.125（2/3）→本批 0.377（3/3），Faithfulness 1（1/3）→0.783（3/3），覆盖不同不能直接写成全面质量提高。共同两题 F1 为 0.125→0.400，仍只是两个已调试 dev 样例的描述性对照。Workflow F1 0.223→0.307（均3/3），Goal 0.667→0（均3/3）；MA F1 0（1/3）→0.370（3/3），也不能忽略覆盖变化。总体质量仍不达标，没有以最高指标包装结果。

### 原生判定口径与质量问题

单跳 P&E Faithfulness 的 statement/NLI 轨迹显示：三项 super-step 事实被判支持，“封存文档没有 thread_id 完整明确说明”被判不支持，因为裁判输入的完整源正文实际包含主键与恢复说明。这是选段不足导致的错误缺口声明，不是完整资料真的没有该事实；Faithfulness 使用完整 selected source body，而不是 writer 可见摘录或逐引用校验。

P&E 多跳原生 Goal verdict=0 的理由包括遗漏 checkpoint 本身不能保证外部写入 exactly-once，也认为恢复方法描述及额外建议与 reference 不符。保留原判定：既有答案完整性/边界问题，也有二值 Goal 对短 reference 和额外表述的敏感性；不能把裁判理由自动当成每句话的事实真值，不能改 gold/提示来挽回分数。P&E/MA 多跳 Faithfulness=1 仍可 Goal=0，runtime completed 也可 Goal=0。

Workflow 与 MA 版本题的核心回答非常接近，均答出 RunnableConfig 与直接传 writer，F1 都为 0.67、Faithfulness 都为 1，却分别 Goal=0 / 1。Workflow 的裁判理由要求额外说明 `<3.11` 的 asyncio context 原因及“不是所有 streaming 均不可用”的边界；这一结果存在裁判一致性/粒度风险，不能把 0/1 差异当成确定的模式优劣。没有重评挑分；后续须用冻结 rubric 与独立人工校准审计裁判，再登记新实验，不能回写本批。

## 留样与下一步

研究与评分结束后复核 185 份源文件及快照哈希全部通过，HEAD、新测试哈希保持不变。实验数据、轨迹、Provider 计量与失败/缺口都保留，未做整体 Git 提交。

- 研究 manifest：`../../tmp/minimal-plan-real-answer-20261003/manifest.json`（本地实验留样）、9 条完整研究记录：`../../tmp/minimal-plan-real-answer-20261003/records.json`（本地实验留样）、研究来源快照：`../../tmp/minimal-plan-real-answer-20261003/source_snapshot/`（本地实验留样）。
- 原生评分：`../../tmp/minimal-plan-real-answer-quality-20261003/quality_scores.json`（本地实验留样）、评分尝试与裁判理由：`../../tmp/minimal-plan-real-answer-quality-20261003/attempts.json`（本地实验留样）。
- 严格身份与统计：`../../tmp/minimal-plan-real-answer-comparison-20261003/comparison.json`（本地实验留样）。

本轮已完成批准的提示改动、回归和唯一复测，不等于可靠产品已完成。下一步优先独立设计“完整关键事实选段 + 可靠引用构造”，随后修正回答完整性/错误缺口声明，并对 Goal 裁判做独立校准；不先扩大调用预算或放宽证据门禁。Report、真实联网端到端、未见测试集、多次重复、不同裁判与独立人工盲评尚待验证。
