# 待办进度更新：实现与同预算校准

## 实现范围

用户确认 2026-10-02 规格后实施。仅修改共享研究系统指令第一条与 write_todos 工具说明：首次仍初始化 2–5 个具体步骤，此后仅在已观察到的进度或计划变化时更新，未变化不重复提交；可与下一步研究工具同批，不能把同批尚未返回的请求提前标为 completed。

完整列表提交、未完成待办和来源门禁、原文支持校验、工具授权、错误与恢复保持不变。没有修改状态/schema、execute_batch、ExecutionPolicy、预算、模型、重试或评分。此改动是模型提示契约，不是宿主强制去重或 todo→工具成功的因果校验。

## 离线验证

- 测试夹具先修正了两个错误假设：read_evidence 返回带坐标的 passages，而不是假定的 evidence.view 事件；EvidenceDraft 按现有字段构造。未修改生产接口迁就测试。
- 干净 RED：6 failed / 7 passed；六条失败均为真实共享节点传给模型的旧指令缺少进度契约，保护回归已经通过。
- GREEN 定向回归：77 passed，含三模式、批处理、checkpoint 恢复不重放 search/fetch、真实授权/原文位置、未完成计划及强退出保护。两处指令和新测试 Ruff check、format --check 通过。
- 隔离 Ragas 回归：34 passed。完整后端冻结回归：966 passed / 2 deselected（114.68 秒）。

依 code-review-and-quality 从正确性、安全、可维护性、测试与兼容性复核；对照上一批 source_snapshot，生产代码差异只有两个文本块。离线指令消费测试不证明真实模型省调用，真实效果单独测量。大量先前工作树改动保留，未整体提交；HEAD 不代表全部实现，以 manifest 文件哈希与快照复现。

## 付费前登记

规格与批次 ID 日期为 2026-10-02，实际执行跨至 2026-10-03（Asia/Shanghai），保留已登记 ID，不创建挑选结果的新批次。

| 项目 | 固定值 |
| --- | --- |
| 批次 | todo-progress-real-answer-20261002 |
| 题目 | single_hop-dev-01 / multi_hop-dev-02 / version_boundary-dev-02 |
| 模式 | plan_execute / workflow / multi_agent，每题每模式一次，共 9 条 |
| 资料/模型 | 7 篇冻结官方文档，本地 search/fetch；真实 doubao-seed-2.0-lite，temperature=0，输出最多 4096 token |
| 输出 | Answer，最多 2000 字符；不测 Report，长时记忆关闭 |
| 每运行上限 | 40 逻辑模型调用 / 80 Provider 尝试 / 24 工具入口 / 12 分支轮 / 360 秒 |
| 整批上限 | 360 逻辑调用 / 720 Provider 尝试 |
| 评分 | 隔离 Ragas 0.4.3，原模型/配置/标准，最多 144 次 Provider 尝试 |
| 排除 | 不新增 baseline、不运行 test split、不改 gold、不自动重跑或扩预算、不重复评分挑高分 |

规范化 dataset 哈希 `44da14cc98057d2aa763c0c2117147b71b13167ceeb63ee137aa12c4e0a69dec`、corpus 哈希 `ffd9e00644024250f508a0d27054c3b96b68e4065b5f0a1ab520ac9648104b8f` 已按 DTO 内容校验，与原 analysis-card 一致。三个输出目录均不存在；仅验证凭据存在，没有导出凭据。Gold 只进入评分侧。

运行命令见 [实施计划](../superpowers/plans/2026-10-02-todo-progress-efficiency.md)。启动前完成完整离线回归；启动后冻结源码/HEAD、保存 manifest 与逐文件 SHA-256 验证的 source_snapshot。

## 结果与解释边界

研究已结束，CLI 退出码 1：3 completed / 3 partial / 3 failed，失败全部为 RequestLimitReached，均无答案。三条 completed 和三条 partial 均有非空引用回答；answered=3，只表示没有 response_partial_reason，不等价于有答案=6。没有新增实时联网调用，也没有将失败补跑。

研究实际 247 逻辑调用 = 247 Provider 尝试、131 个工具入口，input=1,072,962 / output=97,002，missing usage=0，artifact_errors=0，Provider API 错误为 0；费用没有可靠价表，为 null。工具入口包含缓存/读取，不等于网络请求或 write_todos 次数。

| 题目 | 模式 | 状态 / 原因 | 逻辑 / Provider | 工具入口 | 纯待办轮 | 研究分支 | 秒 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| single_hop-dev-01 | P&E | completed | 21 / 21 | 9 | 4 | 3 | 223.26 |
| single_hop-dev-01 | Workflow | partial / insufficient_evidence | 17 / 17 | 10 | 2 | 2 | 81.21 |
| single_hop-dev-01 | MA | partial / max_follow_ups_reached | 17 / 17 | 9 | 2 | 2 | 110.53 |
| multi_hop-dev-02 | P&E | partial / max_replans_reached | 35 / 35 | 24 | 4 | 3 | 236.03 |
| multi_hop-dev-02 | Workflow | completed | 20 / 20 | 9 | 5 | 3 | 107.18 |
| multi_hop-dev-02 | MA | failed / execution_error | 40 / 40 | 20 | 16 | 5 | 66.61 |
| version_boundary-dev-02 | P&E | failed / execution_error | 40 / 40 | 21 | 14 | 5 | 192.20 |
| version_boundary-dev-02 | Workflow | completed | 17 / 17 | 8 | 5 | 2 | 83.32 |
| version_boundary-dev-02 | MA | failed / execution_error | 40 / 40 | 21 | 15 | 5 | 63.51 |

实验身份 `87f02d49dca9c438a71c5d80b060d6b2e0b632aa10644b68911cb72008dc61a0`；HEAD `a930828c0c17d77970d48e7436b92f17caae007f`，工作树 dirty，185 份 manifest 文件已复制并逐份 SHA-256 校验。研究期间复核 source_identity 差异为 0。模型、limits、数据哈希、输出/记忆/重复次数均与上一批完全一致；受测源码仅两个指令文件变化。

### 与上一批的开发诊断对照

纯待办轮定义为工具调用非空且全为 write_todos 的模型轮，不是网页请求数。上批 111/281=39.5%，本批 67/247=27.1%；计数减少 44 轮（39.6%），全部逻辑调用减少 34 次（12.1%）。这是两个小规模实测批次的描述性差异，不能当作预期生产节省或单一因果收益。

| 模式 | completed 上批→本批 | 非空答案 上批→本批 | 逻辑调用 上批→本批 | 纯待办轮 上批→本批 | 分支 上批→本批 |
| --- | ---: | ---: | ---: | ---: | ---: |
| P&E（主模式） | 0→1 / 3 | 1→2 / 3 | 115→96 | 48→22 | 11→11 |
| Workflow | 0→2 / 3 | 3→3 / 3 | 84→54 | 34→12 | 8→7 |
| Multi-Agent | 0→0 / 3 | 2→1 / 3 | 82→97 | 29→33 | 9→12 |

整体失败仍为 3 条，但所在题目变化；MA 覆盖退步，不得只呈现 P&E/Workflow 的正向变化。P&E 单跳用 21 次完成，而上批在 40 次失败；实际时间从 147.32 秒变为 223.26 秒，不能声称调用下降就使耗时下降。分支数按不同研究 query/assignment 的轨迹标签计数，不等于预先规划的查询总数，未执行完的查询也不能计为完成。

### 原生 Ragas

评分结束，退出码 0；46 / 144 次 Provider 尝试，input=129,943 / output=55,044，missing usage=0，费用 null。研究加评分共 293 次尝试，input=1,202,905 / output=152,046，未重评。裁判配置与上批完全相同，scorer_sha256 仍为 `69144d3c8faeb2f2c77bd68c5139e435baa94f2b19ddbcea2064246c80c17688`。

27 个指标槽位为 17 ok / 10 N/A / 0 error。N/A 是三条无答案运行的九项，以及 P&E 多跳完整 selected source body 超过原有 100,000 字符 Faithfulness 输入上限的一项。没有给 N/A 或失败补零，没有临时裁剪正文。

| 模式 | completed | partial / failed | 事实 F1（有效/全部） | Faithfulness（有效/全部） | Goal（有效/全部） |
| --- | ---: | ---: | ---: | ---: | ---: |
| P&E（主模式） | 1/3 | 1 / 1 | 0.125（2/3） | 1.000（1/3） | 0.500（2/3） |
| Workflow | 2/3 | 1 / 0 | 0.223（3/3） | 0.800（3/3） | 0.667（3/3） |
| Multi-Agent | 0/3 | 1 / 2 | 0.000（1/3） | 0.667（1/3） | 0.000（1/3） |

| 题目 | 模式 | F1 | Faithfulness | Goal |
| --- | --- | ---: | ---: | ---: |
| single_hop-dev-01 | P&E | 0 | 1 | 0 |
| single_hop-dev-01 | Workflow | 0 | 0.5 | 0 |
| single_hop-dev-01 | MA | 0 | 0.667 | 0 |
| multi_hop-dev-02 | P&E | 0.25 | N/A | 1 |
| multi_hop-dev-02 | Workflow | 0 | 0.9 | 1 |
| multi_hop-dev-02 | MA | N/A | N/A | N/A |
| version_boundary-dev-02 | P&E | N/A | N/A | N/A |
| version_boundary-dev-02 | Workflow | 0.67 | 1 | 1 |
| version_boundary-dev-02 | MA | N/A | N/A | N/A |

这些是 available-case 均值，不是失败计零的全题事实准确率。P&E 的 Faithfulness=1 只有 1/3 覆盖，不能写成所有回答引用正确率 100%。Faithfulness 看 selected source 完整正文，不是 writer 可见片段/逐引用蕴含；Goal 看 question/final answer/reference，不看宿主完成状态或支持链。多跳 P&E 为 partial 却 Goal=1；多跳 Workflow completed 且 Goal=1，F1 仍为 0。三个指标不能互换或选最高项包装。

P&E 上批 F1=0.310（1/3），本批 0.125（2/3），评分覆盖不同，不把均值变化当因果质量变化；共同可评分的多跳题 F1 从 0.31 到 0.25。Workflow 三题覆盖相同，F1 均值从 0.243 到 0.223；单跳 0→0、多跳 0.40→0、版本 0.33→0.67。MA 评分覆盖从 2/3 退到 1/3。未证明总体事实质量改善，不能只挑版本题提高的分数。

首条 P&E 的裁判原始返回已核对：Faithfulness=1、F1=0、Goal=0 并非输入缺失。原生 F1 的 low atomicity 把答案分成两个复合 claim，裁判对它们都给 0：超步骤的额外定义不在短 reference 中；thread_id 那条额外描述也不能全部由短 reference 推出。反向判断认可“super-step boundary”，但不认可遗漏的无 thread_id 无法保存/加载状态及 pending writes 区别。Goal 则明确表示前两个核心结论吻合，但缺少 reference 的 pending writes 边界。这同时暴露回答遗漏和短参考/复合 claim 粒度敏感性，不能简单把零分解释为每个事实全错，或一概归咎跨语言。原模型、gold、默认粒度和分数均保持不变，没有追加裁判调用验证该诊断。

### 已核验的真实轨迹问题

1. 单跳 Workflow 与 MA 的 evaluator 仍表示 thread_id 解释所在片段不完整。MA 研究员虽有解释，中央评估没有接受完整来源支持，补查又没有新的合法 assignment；研究员散文不是可直接替代原文的证据。
2. 多跳 P&E 的 finding-2 引用文本确实在 evaluator 可见原文中，但生成的 passage_id 为 `p-173589e4850367c1ab3a1b40b8c7827`，可见标签实际为 `p-173589e4850367c1ab3a1b40b8c87827`。引用了不存在的标签，原文门禁拒绝 r2 覆盖，补查没有新合法任务。这是 ID 复制错误，不是没有抓到原文；未关闭验证或把错误标签自动视为正确。
3. 版本 P&E 规划出 6 条近义查询及重复答案要点，实际进入 5 个研究分支。40 次中 1 次规划、39 次研究，未进入 evaluator/responder。MA 多跳与版本也在 40 次上限处失败。没有生产运行级调用预留；本批 global cap 来自 eval CountingModelGateway，不能宣称已实现生产配额编排。
4. 多跳 Workflow 达到运行 completed，但 final answer 有“检查点保存器会在外部写入和 interrupt 调用完成后保存完整图状态”“彻底消除恢复时产生重复副作用的风险”等强断言。记录这些待审质量问题，不能将通过结构/原文字符串验证当作语义蕴含或端到端可靠性；事实评分另计。

下一步需独立设计最小规划/回答额度预留、减少长 ID 抄写错误，以及评估视图的完整证据送达。本轮未实施这些更广泛行为改变；只完成批准的待办指令调整与单批校准。

### 留样与严格统计

compare_cli 对评分输入 digest、实验身份、裁判身份与数据/语料元数据校验通过，退出码 0；没有新 baseline，全部配对 n=0、delta/CI=null，没有拼接旧基线。评分输入 digest 为 `2bab142d0a663b2d2b0e2a012644b6284f6899645bba63132cd614a339f44348`。研究、评分结束后 source_identity 再核对，185 份文件差异为 0。

原始记录保留于 `tmp/todo-progress-real-answer-20261002/` 的 records.json、quality_eval.json、manifest.json、samples/ 和 source_snapshot/；原生评分及逐次裁判请求/返回位于 `tmp/todo-progress-real-answer-quality-20261002/` 的 quality_scores.json、attempts.json、identity.json；统计覆盖/排除位于 `tmp/todo-progress-real-answer-comparison-20261002/comparison.json`。没有导出 .env。请求含任务与公共文档，公开分享前仍需数据审查。

新增测试另留为研究目录下 `test_todo_progress_contract.py`，SHA-256 `8a1a0e79099197cf044ba0ac98317c25bf9ec7a8656bd73939496a4a02a800d5`；它不是 manifest 的生产源码身份文件。source_snapshot 的 185 份不包含完整 backend/tests 工作树，不能声称仅凭该快照就能复现所有 966 项测试；完整测试结果对应保留的当前工作树与上述实际命令。

这只是三道已用开发题、无重复的校准，真实模型搭配本地冻结资料，不是生产联网 E2E、独立测试集成绩或商业产品对比。没有新 baseline，配对 n=0，delta/CI 不解释；旧批与本批按模式对照仅是开发诊断，不证明因果效果。Ragas 同模型裁判、语言/claim 粒度与完整正文输入限制仍存在，独立人工复核为 0；不把 Goal 高分当作事实准确或系统完成。
