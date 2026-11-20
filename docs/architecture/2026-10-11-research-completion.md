# 研究完成与取材优化

日期：2026-10-11。接续 [10 月 10 日真实 API 失败定位](2026-10-10-deepseek-live-retest.md)，保留历史结果。

本文为本日较早阶段记录；最新根因、边界修复及复测见[研究边界修复](2026-10-11-research-boundaries.md)。下文“最后／最新”均指本文对应阶段。

## 参考项目与取舍

[Open Deep Research](https://www.langchain.com/blog/open-deep-research) 将明确研究范围、分工研究、缺口迭代和统一写作分开。[Anthropic 的多 Agent 研究设计](https://www.anthropic.com/engineering/multi-agent-research-system) 强调清楚的任务边界、独立上下文和根据结果调整研究方向。这里吸收职责和反馈路径，不迁移框架，也不把更多角色当成完成保证。

本项目继续使用现有 LangGraph、Gateway、预算与证据契约。Plan-and-Execute 顺序执行任务，Multi-Agent 并行执行独立分支；两者集中核验和回答，针对未覆盖需求做有限补查。同一官方 API 的相关行为可以合并取材，多个事实需求不要求对应多个 Agent。

## 完成语义

| 模式 | completed 的含义 | 证据缺口 |
| --- | --- | --- |
| Workflow | 固定研究与回答流程执行结束，返回 workflow_completed | 保留 coverage、research termination、response partial_reason 和 unresolved_gaps；不发起补搜 |
| Plan-and-Execute | 固定需求都有经原文支持的结论，回答通过现有门禁 | 缺口进入 replan；达到上限、无进展或资源耗尽保留 partial |
| Multi-Agent | 分支结果合并后覆盖固定需求，回答通过现有门禁 | 缺口进入 follow_up；停止条件同样有界 |

Workflow 的证据不足不阻止流程完成。取消、预算截断、工具致命退出或回答生成失败仍属于执行未完成；旧 v1 baseline 保留原有语义。`completed` 不能直接用作答案质量指标。评测 CLI 同时检查 answered，空答案不会因 Workflow 完成而通过质量验收。

## 实际修改

1. 普通知识研究执行两条互补检索，交错候选；科研路径保留一次高级检索和一次基础检索，修复同一查询重复派发。
2. 规划增加有界的 `source_domains` 检索提示，经过已有分支上下文传给每条搜索；显式 `site:` 转为 Tavily `include_domains`，同时过滤域名不匹配的结果。路径保留为搜索线索，实际版本仍需抓取和核验。[Tavily 参数说明](https://github.com/tavily-ai/tavily-python/blob/master/_autodocs/configuration.md)
3. 抓取前优先候选 URL 中匹配问题版本的路径；不把标题、域名或搜索摘要当成来源准入。
4. 普通研究按各自负责的事实需求选取独立阅读片段，避免 TaskGroup 相关段落挤掉 gather；读取仍通过真实工具、授权和原文锚点。
5. 为当前 DeepSeek 的 planner/replanner/supervisor/follow_up/evaluator/responder 使用 JSON object 模式。工具研究角色保留工具调用。核验与补查提示给出数据实例，明确字段层级；严格 schema 与一次格式修复继续保留。
6. 核验失败但已取得来源时不直接结束，而是有限补查。模型预算耗尽直接退出；没有新证据、结论或覆盖时停止，避免重复搜索。
7. 真实运行发现 SQLite 读写锁冲突，应用连接启用 WAL 和 10 秒 busy_timeout。回归用两个真实连接验证读快照与独立写提交可以共存，不替换存储账本。
8. 真实材料继续定位到父核验的每来源窗口再次丢失独立要点，普通研究改为按需求数量分配 3000–6000 字，保留整体 Token 与引用容量门禁；科研路径不变。同版本官方译文的证据语言不受中文输出要求限制。指定官网资料且已发现匹配版本时优先这批候选。
9. 真实 Workflow 的记忆索引出现重复 ID；索引入口按 ID 保留最新版本后再提交，新增实际 Chroma 与检索器回归。原始矩阵中的索引失败仍保留，不改成成功记录。
10. 短回答的单来源材料窗口由 3000 改为 6000 字，避免答案长度上限导致已核验的多个事实被再次截掉。整体 TokenBudget 不变；确实超过材料容量仍返回 response_evidence_context_limit。
11. 协议解析边界可恢复明确的字段错层：将 coverage 内的已知顶层字段移回顶层，再执行完整 schema 校验。根部与内部冲突、未知字段、无效值或引用仍拒绝，不自动赋予来源资格。格式重试仍最多一次。最终审查显式要求最多 8 条修改原因、每条 300 字，不接受超限输出；比较结论保留正常／异常路径等触发条件。
12. 规划列表使用任务说明而映射使用搜索词时，仅在 query_targets 与 task_briefs 键一致、每个任务明确声明相同 search_queries 时对齐；所有需求分工仍严格校验，歧义继续降级。补查核验时已支持来源与新来源交错进入同一有限窗口，避免取得新证据后遗忘另一项已有覆盖，不扩大来源数量上限。
13. 科研取材和已明确缺口的定向补查读取结束后直接交接原文锚点，去掉父核验之前的重复分支摘要。科研分支仍由模型选材，普通首次研究仍保留分支整理；集中核验继续从当次原文提取结论、检查日期和资格。读取失败、无片段和强制停止不走成功交接，取材完成不代表研究完成。

14. 核验规则作为系统指令，模型规划简报与纠正材料作为任务数据；明确回答语言与证据语言分离，保留原始用户明确的限制。JSON、来源和逐字支持继续严格校验。

这些变化集中在现有边界，没有新增 Agent 框架、服务或依赖。JSON object 保证语法形态，字段和证据含义仍由应用校验。

## 真实测试范围

配置模型 `deepseek-v4.1-flash`，实际返回 `deepseek-v4-1-flash-260910`。使用既有火山方舟和 Tavily 凭据。当前本地 `.env` 使用 `DEEPTRACE_MODEL_THINKING=disabled`；真实探针确认 JSON object 输出可解析，reasoning Token 为 0。[供应商思考参数](https://docs.volcengine.com/docs/ark/deep-thinking?lang=en)

矩阵通过生产 `build_harness_runtime` 与 LocalResearchRuntime，使用真实模型、搜索和网页抓取。每题独立 SQLite／Chroma，保留 BGE-M3 语义记忆和最终事实审查。未连接真实 MySQL／Redis。

输出上限仍为 16,000，全局 20 次模型调用／100,000 输入 Token，研究 600 秒／额外收尾 120 秒，首批来源目标 3。没有通过扩大预算或放松来源规则取得通过。wall time 包含记忆整理、索引和回答，组装另计。

## 运行结果与质量边界

同题为“仅依据 Python 3.11 官方文档，比较 TaskGroup 与默认 gather 在子任务普通异常、取消及清理时的行为，并说明吞掉 CancelledError 的影响。用中文回答。”追加跨文档题涉及 asyncio 与 contextvars.copy_context() 的复制、复杂度与隔离作用。

下表为核验规则分层修复后保存的生产运行，使用最终研究代码。文档示例为本轮先前保存的运行，其独立循环没有受研究核验修改影响。前序成功、失败和未充分回答的阶段样本均保留，未覆写。

| 样本 | 状态／终止原因 | 完整耗时 | 模型调用 | 总 Token | 固定需求覆盖 |
| --- | --- | ---: | ---: | ---: | --- |
| Python / Workflow | completed / workflow_completed | 71.617 秒 | 7 | 41,711 | 1/6 |
| Python / Plan-and-Execute | completed / completed | 54.212 秒 | 6 | 50,271 | 5/5 |
| Python / Multi-Agent | partial / max_follow_ups_reached | 113.311 秒 | 10 | 78,452 | 4/5 |
| 跨文档 / Multi-Agent | completed / completed | 110.854 秒 | 10 | 68,864 | 4/4 |
| 量子研究 / Plan-and-Execute | partial / max_replans_reached | 311.559 秒 | 17 | 102,370 | 1/4 |
| 独立文档循环 | completed | 2.457 秒 | 2 | 923 | 不适用 |

Workflow 的 completed 表示固定流程执行结束，当前需求覆盖为 1/6；research/response 的证据判断、公开缺口与执行状态分别保存，不把执行完成当作质量通过。Plan/Multi 的 completed 仍要求固定需求覆盖及现有回答门禁，不能只以搜索或任务列表结束为依据。

最新同题 Plan 完成 5/5；Multi 则为 partial、覆盖 4/5，不是同题全部通过。Multi 已读官方原文中的清理后传播、吞掉 CancelledError 可能使结构化并发异常等警告，核验仍认为缺少对取消与清理影响的更具体说明；两轮补查后停止。应检查它是否将文档确认的警告扩大成必须给出内部机制，不把终态人工改为 completed。前阶段 f67562e7c48b 曾在 39.752 秒、5 次调用、27,983 Token 下 completed（4/4），规划与核验结果不同，不能替代最后复跑。

跨文档运行 6247c88c2674 在两轮补查后 completed，覆盖 4/4，引用 Python 3.11 西班牙文 asyncio-task 与中文 contextvars 官方原文，response partial_reason=null。初始两个 researcher 调用重叠检查为 True；不据此推导普遍提速。此前 6850b97d718f 为 partial（1/3），核验把“中文回答”错误扩大为“中文证据”；修复采用系统核验规则与非权威规划数据分层，来源身份、版本和逐字引用门禁仍保留。

固定失败材料的单阶段核验重放（frozen-evaluator-authority-final）用当前系统规则产生 2/3 覆盖，不再拒绝日文／西班牙文官方原文，但要求原文直接并列比较两对象，第三项仍 missing。这是另一种额外添加的要求；没有自动改成 covered。该探针 7.106 秒、1 次 API 调用、11,268 Token，仅是核验阶段，未执行搜索或宿主完整准入，不混入端到端成绩。另一个较早材料探针与本地封装校验失败记录也保留。

年度量子题最后为 partial/max_replans_reached，覆盖 1/4。未覆盖项的程序保存原因：unsupported_requirement_coverage；仅见finding-5的纠缠增强传感理论协议，未发现2026年量子传感/精密测量的实验成果原文。；unsupported_requirement_coverage。这轮不只有取材问题：r3封存需求允许理论或实验，核验仍要求实验成果；r4规划另外加入实验完成时间，原用户只是询问年度进展。部分引用未通过宿主支持校验，核验的字段冲突与一次抓取超时也保留。不能将所有partial原因归为没有资料。此前 balanced 阶段 47f823de329e completed（3/3、177.023 秒、17 次调用、92,711 Token），直接交接阶段 55cb249bda76 partial（2/3、175.617 秒、14 次调用、79,825 Token）。它们的规划与材料不同，不能选择成功轮次声称稳定完成，也不能把原文不足改为成功。

引用、覆盖与语义正确分别核查。先前同题 Multi 答案中“吞掉 CancelledError 会破坏取消传播与清理”比原文“可能无法正常工作”更强；最新跨文档答案将 copy_context 的用途概括成使线程／任务拥有独立映射，也应进一步区分复制对象与实际进入或传递该上下文的使用步骤。一次事实审查可能遗漏这类措辞与机制边界，不能给出准确率或宣称整个领域研究已充分。

## 验证与恢复核对

- 最后完整离线回归：1432 passed、2 deselected，144.17 秒；`uv run --no-sync pytest -m 'not real' -q`，日志 offline-pytest-authority-final.log。
- 当前代码真实 pytest：2 passed、1432 deselected，134.41 秒，日志 real-pytest-authority.log。联网 Workflow 冒烟继续要求真实抓取、引用和 response partial_reason=null；没有降低断言。全量回归中的 scripted 核验现在读取系统规则与任务数据，修复了旧测试只看末条 human 消息引发的两项失败。
- 相关改动 Python Ruff 与 git diff --check 通过。引用过量、冲突／未知字段、未知引用、无覆盖、原预算限制及真实 Chroma 去重回归保留。
- 全部 25 条生产研究运行的 SQL 预算通过新连接／新网关只读恢复，200 项核对全部通过，包括调用、usage、未知用量、原始限制／开始时间和保守输入消耗。失败轮次也纳入。
- 表中研究样本共 73 条已引用支持通过正文哈希、版本、坐标与逐字 quote 核对，来源准入与最终引用 ID 一致。中间无回答失败的记录单独保留，未算作成功引用验证。

恢复没有再调用模型或搜索、没有延长原始截止。原始模型消息、响应、引用正文、阶段事件与 SQLite 位于本地忽略目录，按每轮独立保存和计量；探针与 pytest 单独记录，不并入生产运行表。

## 剩余优化方向

优先建立小型语义反例集：回答语言与证据语言分离、基于分别支持的事实进行比较、可能／必然措辞、操作用途与自动执行机制。按原任务和封存需求评审核验误拒绝、回答过度推断，而不是继续增加补查轮次。开放年度题还需改善原始成果发现与日期核对；保持轮次、预算和无进展停止，不保证任意题目均 completed。

本轮已恢复多条真实完成路径；稳定完成率与端到端语义准确性尚未建立，不以单题状态替代质量结论。

## 诊断记录

首次运行误写配置名称 `MODEL_THINKING`，实际仍为 auto；记录保留在 `.local-notes/research-completion-auto-2026-10-11`，不纳入 disabled 矩阵。随后一轮发现来源域名未结构化传递和 SQLite 锁冲突，保留在 `.local-notes/research-completion-discovery-v1-2026-10-11`。这些属于定位记录，不当作最终版本成绩。

最终及中间阶段的原始产物位于 [结果目录](../../.local-notes/research-completion-final-2026-10-11/)，早期取材阶段另存于 `.local-notes/research-completion-2026-10-11`。模型消息、响应、引用正文、状态和阶段事件仅保存在本地忽略目录。探针、真实 pytest 与矩阵分开计量。所有失败与不充分交付保留，不用重跑覆盖原记录。

## 面试讲法

可以讲：“我发现失败不只在模型能力：规划的来源限制没有传到检索、阅读窗口漏掉对比对象、JSON 的字段层级不稳定。把约束传到现有工具边界，保留原文和覆盖核验，再用真实 API 检查回答。固定 Workflow 的完成表示流程结束；需要补查的策略则按覆盖推进，遇到预算和无进展仍诚实停止。”

单题采样不能推导准确率、P95 或普遍提速。此次同时改变 thinking 与取材／提示，端到端差异不能归因于某一项代码。独立文档示例仍只验证只读工具循环，不代表已实现完整 Coding Agent。
