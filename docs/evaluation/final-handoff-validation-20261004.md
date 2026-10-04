# 最后一轮证据交接：验证记录

日期：2026-10-04。用户批准主模式真实联网 completed、F1≥0.80、来源合格后冻结；三模式各一次，其他模式如实报告。

## 实施与离线证据

修复共享已读取材，删除评估侧独立通用词排序；原文坐标与有效 anchor 范围保留，未读间隙重置章节上下文。已有有效支持先保留。全局评估预算同优先级内按来源交错，完整阅读组原子进出。

同一 evaluator 输出逐来源 eligible/ineligible/uncertain；未知、重复、遗漏、无可见原文均不默认接受。过滤 findings 后重新归一 coverage，映射经三模式 state/ResearchOutcome 传给 Writer。Writer 加载和材料装配均拒绝未批准来源。没有新增 Agent、服务、依赖或模型步骤，没有增加研究轮数/预算，没有修改评分器。

TDD：新回归先验证失败，包括晚读关键条件被泛化窗口挤掉、缺失来源检查仍覆盖需求、Writer 回退带回拒绝 URL。全局预算用例先在500 token通过，收紧至420 token准确复现第二来源条件丢失，交错分配后通过；500不是失败复现，不混计。

新增26项参数展开后的用例。完整回归初次92失败，主要为旧脚本没有 source_checks；更新仅限测试/离线脚本协议后91项旧失败通过。剩下报告夹具在空会话只问“请生成报告”，脚本却自行研究LangGraph，没有适用可见材料；补充实际主题，保留引用/路由原断言，不放宽准入或改为partial断言。

完整离线最终：**1213 passed，2 deselected，129.67秒**。独立 `.venv-ragas` 的 `evaluation/tests`：**34 passed，18.83秒**。目标变化文件 Ruff（缓存工具环境）通过、compileall 通过、跟踪文件 whitespace 检查通过。

全仓库 Ruff 另有67项既有/范围外问题，没有为本轮全部重写；“目标变化文件检查通过”不等于全仓库 lint 全绿。生产 `.venv` 无ruff，使用缓存 `uv tool run --offline ruff`，没有新增项目依赖。误指向 `tests/real/test_eval_quality.py` 的独立环境尝试因项目未安装而失败，不算成功测试；34项来自正确的独立 `evaluation/tests`。

按 code-review-and-quality 自审正确性、复杂度、架构、安全和性能；技能引用的两个补充checklist文件不存在，只使用已读主文件，不声称独立或多模型评审。保留历史DTO解码；历史None不是新评估的默认准入，当前实时缺失检查产生uncertain映射。来源适用性仍有模型判断边界，不宣称绝对可靠。

## 真实实验登记

- 前缀：`final-handoff-answer-20261004`，新产物目录；封存：`tmp/final-handoff-freeze-20261004/source_snapshot`，不含.env。
- 实验身份：`d0d32304f479b185dbbd69dff4fe0957f9c0c1c2e70f977a8a99671c8718fb3e`。
- 源码身份：`fd3ee8df47da5f48805039646bf01ded835a31d9118ba829c86d5ec52fde0523`。
- 数据：已有单题 `asyncio-live-01`，已知诊断题，非heldout。gold只进评分侧。
- doubao-seed-2.0-lite、temperature=0、输出4096、Answer2000字符、记忆关闭；每分支12轮。
- 每运行40 logical/80 Provider/24 Gateway/360秒；批次120 logical/240 Provider。评分独立Ragas0.4.3，一次，上限48 Provider。
- 预检与上轮除源码/Git/新前缀外逐字段核对控制一致，评分器hash相同。策略单列 `shared-read-selection-source-admission-v3`。

## 最终结果与冻结

三模式各一次真实研究与一次评分均已结束，研究运行均为completed。主模式F1=1.00、指定3.11官方来源正确，达到用户约定收尾门槛；源码与测试的冻结hash复核通过，不继续修改实现。Workflow仍有版本误判，不能宣称全部模式通过来源验收或全部指标通过。

| 模式 | 状态 | Factual Correctness F1 | Faithfulness | Goal | 指定来源 | 研究耗时 | 总token | 搜索尝试代理数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Plan-and-Execute（主） | completed | 1.00 | 0.9000 | 0.00 | 合格 | 116.29秒 | 62191 | 1 |
| Workflow | completed | 1.00 | 0.8571 | 0.00 | 不合格 | 107.86秒 | 114411 | 3 |
| Multi-agent | completed | 0.89 | 0.8889 | 0.00 | 合格 | 93.07秒 | 66038 | 2 |

全部9项评分status均为ok，错误为空，不存在将评分调用失败记为0的情形。Goal的0是原始有效评分结果。研究总Provider尝试52，输入218511、输出24129、总token242640，全部usage完整、工具重试0。评分另计24/48次Provider尝试，输入65716、输出35740、总token101456，全部usage完整；价格未知，cost=null，不推算人民币或发票费用。

主模式分支实际5/3/3轮，Workflow为9/6/6，Multi-agent为6/5；这些是各分支轮数，不能把它们的和当单分支上限。三模式本轮均未耗尽12轮分支上限。主模式搜索1、抓取1、读取3；Workflow搜索3、抓取3、读取7（其中抓取1次为复用/缓存路径）；Multi-agent搜索2、抓取2、读取3。搜索代理数不是搜索供应商账单。

严格来源审计：主模式与Multi-agent最终仅引用官方3.11语言变体页面；Workflow引用默认`/3/`路径，未满足指定3.11版本。Multi-agent的实际评估拒绝了3.14来源；Workflow却将默认版本误判为eligible，保留该失败，不在冻结后继续修补。

主模式Goal原始值0：`attempts.json`的索引6把详细最终答案概括为“已经完成对比/说明”的end_state，索引7认为其不含参考答案的具体行为，给verdict=0。评分输入是完整问题与答案，此处信息丢失发生于judge提取步骤，不是评分器遗漏了最终答案。本轮不修改或重评分，保留0；不能宣称全部指标通过。

主模式Faithfulness9/10，9条技术陈述均被支持，1条出处标题因评分context没有完整标题判0。标题/URL的来源身份另行审计，来源检查不能用body-only忠实度替代。

## 改善范围与产物核对

相对紧邻上一轮同题主模式：F1由0.86变1.00，partial变completed；196.36→116.29秒（下降40.8%），163130→62191 token（下降61.9%），搜索尝试代理数5→1。这是单题、各一次、非heldout的诊断比较；旧轮未通过完整验收，不能声称跨任务稳定收益、统计显著或成功成本配对证明。Multi-agent最终回答遗漏了gather(return_exceptions=True)细节，不能因为F1≥0.80而说答案逐项完整。

`final-handoff-summary.py`完成源码/测试冻结hash、配置登记身份、评分器身份和逐字引用范围复核；字面审计记录13条候选笔记、23个归一支持、Writer缺失支持0、产物错误0。审计定位与可见性不等于语义蕴含证明；本题严格版本URL规则只用于事后诊断，没有放进生产判断。内置报告的字面gold URL命中不是本表的质量F1，语言变体来源另行核验。

- 冻结登记：`../../tmp/final-handoff-freeze-20261004/registration.json`（本地实验留样）
- 配置身份：`../../tmp/final-handoff-answer-20261004/manifest.json`（本地实验留样）
- 三模式真实回答及轨迹：`../../tmp/final-handoff-answer-20261004/records.json`（本地实验留样）
- 一次原始评分：`../../tmp/final-handoff-answer-20261004-quality/quality_scores.json`（本地实验留样）
- 评分原始尝试：`../../tmp/final-handoff-answer-20261004-quality/attempts.json`（本地实验留样）
- 最终统计及限制：`../../tmp/final-handoff-summary-20261004.json`（本地实验留样）
- 字面引用审计：`../../tmp/final-handoff-audit-20261004.json`（本地实验留样）

结论：主模式按确认门槛收尾，停止实现修改；其余模式与Goal限制如实保留。另行交付面试设计背诵版与实测事实文件，不把理想成熟方案写成已上线经历。
