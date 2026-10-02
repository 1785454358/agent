# 第二轮：按实际进度更新待办

## 目标和范围

用户回复“继续”，并选择“先修待办空转：仅在进度变化时更新，可与研究工具同批；保留未完成待办和证据门禁”。本轮只修共享研究提示与 write_todos 工具说明，不同时收紧初始规划数量、增加运行级预算系统、改评估 schema 或来源选段。

主验收仍为 Plan-and-Execute + Answer，三模式一致验证；Report 不合并评分。设计追求最小、共享、可验证，不新增 Agent、服务、模型调用、状态机或持久化字段。

## 根因证据

上一批 planning-gap-real-answer-20261002 的九条运行：0 completed / 6 partial / 3 failed；281 次逻辑与 Provider 调用，111 个模型轮仅请求 write_todos（39.5%）。P&E 单跳与版本各有 17 个纯待办轮，均在 evaluator/responder 前耗尽 40 次调用。

`harness/prompts.py` 明确要求“在后续每轮用 write_todos 更新每项状态”。这是一条共享行为指令，不是模型自发无因重复。执行路径为 prepare_messages → researcher model → execute_batch → observe → next model；每个纯待办响应仍占一个完整模型调用和分支轮次。

`agent_tools.py` 已允许同批待办与研究工具，待办本地写入有序、每个 call 都有匹配 ToolMessage；无需为了批处理重写调度器。`ExecutionPolicy` 在存在证据、模型结束且无未完成待办时才允许分支 completed；父策略仍检查 requirement 原文支持及受控退出。

生产 `_budgets_for_run` 当前配置工具/网络/页面预算；全运行模型调用上限由评测 CountingModelGateway 执行。真正的生产模型额度预留涉及计量与恢复，不把 eval 侧修补包装成生产级预算治理，留作独立设计。

## 方案选择

1. **推荐并已选择：按实际进度更新的共享指令。** 删除每轮强制更新，仅在初始化、已观察到的执行结果带来状态变化、计划确需调整时调用。低改动，无新状态或权限；效果依赖模型行为，真实轨迹验收。
2. 先限制初始规划数量。可减少近义分支，但不能消除共享指令制造的待办轮；当前用户选择先不做。
3. 先接入运行级额度预留。可以保护收尾，但涉及生产模型计量/恢复和并发预留，范围更大；当前不做。

不选择动态隐藏 write_todos 或自动完成待办：前者可能妨碍真正状态变化/结束，后者可能虚构完成；两者都需要额外状态和兼容设计。

## 共享指令契约

保持首次初始化 2–5 个具体待办的现有要求，不修改数据 schema 的 1–20 项上限。后续指导改为：

- 仅在已观察到的进度、失败处理或计划内容确有变化时更新；若与当前计划相同，不重复提交。
- 更新待办不必单独占一个模型轮，可与下一步 search_web / fetch_page / read_evidence 同批。仍遵守现有 URL、证据授权与参数校验，不预测未知的来源 URL 或 evidence_id。
- 只能根据已经返回的结果标记 completed，不能把同批尚未返回的工具请求提前标为成功。失败、未执行或缺口项应保留未完成状态。
- 计划全完成且已获取证据后才允许结束研究；原文阅读、引用、用户约束、工具失败处理与不可信正文边界保持不变。
- write_todos 的描述使用同一进度变化原则，防止工具说明与系统指令互相矛盾；仍提交完整有界列表。

这是提示契约，不是确定性去重器或真实进度验证器。主机当前不会根据待办文本推断工具成功，本轮也不新增这种推断；模型声明完成不能替代父策略证据门禁。不得声称提示更新保证以后零空转或必定 completed。

## 实现边界和兼容性

修改 `backend/src/deeptrace/harness/prompts.py` 的研究指令第一条及 `backend/src/deeptrace/harness/agent_tools.py` 的 write_todos 工具描述。不改 execute_batch、ExecutionPolicy、工具参数、重试、模型、max_iterations、预算、强退出规则或 checkpoint schema。

新增聚焦测试 `backend/tests/harness/test_todo_progress_contract.py`，复用现有共享 Agent/三模式集成与 checkpoint 测试。旧 checkpoint 中未完成待办保持原状，新调用使用新指令，不静默修改计划或历史 tool transcript。

## 验证标准

1. TDD 先验证真实共享节点传给模型的指令不再包含“每轮强制更新”，且系统指令/工具说明均包含按已观察进度更新与不得预标未返回工具完成的契约。提示文本是本改动的接口，但文本测试本身不等于质量提升证据。
2. 运行真实共享 graph，脚本模型只替代外部模型边界：初始化待办 + 搜索同批、已观察搜索后更新 + 抓取同批、原文读取成功后的完成更新，验证 ToolMessage 一一配对、证据授权与引用位置保留、checkpoint 往返/续跑及完成状态一致。脚本轨迹不用于声称真实 API 节省百分比。
3. 未完成 todo、有待办无证据、致命工具失败/取消/预算强退出仍不能 completed；可恢复错误在后续真正恢复后仍可正常完成。批处理如有失败，真实工具错误、预算/取消标记与未执行结果仍保留且一一配对，不用待办声明抹除。父策略无原文支持仍不能 completed。本轮不新增“每个 completed todo 必须绑定成功工具”的确定性校验，不能在测试中要求此新行为。运行现有三模式恢复及证据门禁回归。
4. 全后端 `pytest -m 'not real'`、隔离 `evaluation/tests`；Ruff 在 backend 工作目录检查相关文件。不针对无关旧 lint 修改代码。
5. 真实结果至少同时报告 completed/partial/failed、非空答案数、纯待办轮/全部逻辑调用、分支数、模型/Provider 尝试、工具入口、usage 缺失与 Ragas 分数覆盖。保持原标准，不只报有答案样本。

## 书面确认后的真实 API 边界

实现离线验证完成后，在付费调用前另登记唯一新批次 `todo-progress-real-answer-20261002`。沿用同三道已用 dev 题、同 7 篇冻结官方语料，三模式各一次，共 9 条 Answer，不新跑 baseline，不使用未见 test split。

条件与前批一致：doubao-seed-2.0-lite / temperature=0 / 输出 4096 token / Answer 上限 2000 字符 / 长期记忆关闭；单运行最多 40 个逻辑调用、80 次 Provider 尝试、24 个工具入口、12 个分支轮、360 秒；整批 360 逻辑 / 720 Provider 上限。隔离 Ragas 0.4.3 原模型及 scorer、原输入限额，最多 144 次评分 Provider 尝试。

独立输出目录为 `tmp/todo-progress-real-answer-20261002/`、`tmp/todo-progress-real-answer-quality-20261002/`、`tmp/todo-progress-real-answer-comparison-20261002/`。冻结源码/HEAD，保存 source_snapshot 逐份验哈希；保留失败、partial、N/A。不得自动换目录重复整个批次、增预算、改 gold、截短评分来源或重新裁判取最高值。没有新 baseline，配对差异仍为 N/A。

本轮和刚结束的上一批同条件对照，仅作小规模开发诊断；无重复运行、Provider 非确定性、同模型裁判且参考未经人工盲评，不作独立因果或总体质量提升声明。仍不是生产实时联网 E2E，不能预先保证完成。

## 自检和流程状态

- [x] 调查真实轨迹、共享提示、执行/预算边界及最近提交。
- [x] 判断视觉辅助不适用：这是行为与验收契约，无布局/视觉选择。
- [x] 单问题澄清优先级，用户选择先修待办空转。
- [x] 比较待办更新、初始计划数量、生产额度预留三种方向。
- [x] 呈现共享指令及门禁不变设计，用户已确认方向。
- [x] 保存规格并自审：范围仅两个提示入口，无新状态/权限；批处理不得预标完成；离线验证与真实效果区分。
- [ ] 用户审阅本书面规格后，才调用 writing-plans 并实施。本文件尚不是完成实现证明。
