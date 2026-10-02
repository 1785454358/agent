# 第一轮优化：共享规划契约与补查目标

## 目标与已确认范围

用户选择分步优化，先修三模式共享规划与补查，不同时改研究循环和评估输出规模。主验收仍为 Plan-and-Execute + Answer，Workflow / Multi-Agent 一并做一致性回归；Report 不合并评分。

真实开发轨迹显示两个问题：planner 把“只使用冻结文档”等过程约束列为必须由来源支持的 requirement；replanner 同时指向缺失 r1 与已覆盖 r3，现有 `parse_gap_tasks` 因并非所有目标都在 gap_ids 中，整条丢弃，导致 no_new_tasks_to_plan。

本轮不改变模型、数据/参考答案、语义评分标准、证据支持门禁、迭代次数或预算。不新增服务、Agent、调用级校验模型或持久化模型。

## 方案选择

采用共享规划提示/有界输出契约与确定性补查校验。另一个方案是只调三份提示词，改动小，但不能修复整条补查误丢弃；重做全部任务/预算状态机则超出本轮范围，难以归因。

参考 [Anthropic：Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) 中简单可组合流程、对中间步骤做程序校验的原则。本设计的 requirements / execution_constraints 分区及 ID 交集规则是对本项目真实失败的针对性设计，不声称文章或商业 DeepResearch 使用了完全相同的数据结构。

初始规划仍复用既有一次模型调用和 `seal_initial_plan`。三模式共用一段规划指令，明确区分答案要点与执行约束，避免三个地方独立维护相同规则。

## 初始规划边界

- `requirements` 保持 1–6 项 `id / description`；只包含用户要回答、需要来源证明的问题。例如检查点生成时机、thread_id 的作用。
- 规划 JSON 增加可选 `execution_constraints`，0–6 个非空字符串、每项最多 500 字符，供模型明确列出来源范围、语言、格式等约束。旧输出不含此字段仍可解析。
- 该字段只是模型对任务的说明，不是新的执行授权或完成条件；不能覆盖原始问题、会话约束、工具策略或预算，也不作为证据门禁的一项。约束的权威副本继续是完整原始问题与已有用户约束，传给研究、评估、回答阶段。
- 使用共享的有界解析辅助结构校验 requirements 与可选 execution_constraints；无效字段、空 requirements 或无法解析沿用全任务降级。主机继续重新编号 r1…rN。
- 不写中英文关键词过滤器，不凭“包含约束字样”删除 requirement；不能把真正的法律限制、版本限制等研究事实误当执行约束。例如“Python 3.10 的限制”仍是要回答的事实问题。
- evaluator 的共享指令说明：execution constraints 必须遵守，但不单独要求用 Finding 证明“遵守过程”本身。requirement 覆盖仍必须引用经原文支持验证的 finding。

示例输出（查询字段在 MA 中仍为 assignments）：

```json
{
  "queries": ["LangGraph checkpoint super-step thread_id"],
  "requirements": [
    {"id": "r1", "description": "检查点器何时生成完整状态快照"},
    {"id": "r2", "description": "为什么必须提供 thread_id"}
  ],
  "execution_constraints": ["只使用提供的冻结文档"]
}
```

本轮不会新增过程约束检查器，也不能靠类型验证保证模型永远正确拆解语义。完整原始任务不得被摘要替代；不通过缩小原始任务或改 gold 获得完成状态。拆解质量还需真实复测核验。

## 补查目标的确定性规则

解析时提供主机封存的全部 requirement_ids 和当前 gap_ids（missing/conflicting）。gap_ids 必须是前者子集；模型不能提供这两个主机集合。

1. 查询、目标列表及格式先按现有长度/数量校验；重复目标、未知 ID、已派发的归一化重复查询仍拒绝。
2. 目标全部属于封存要求时，按原顺序保留其中处于当前缺口的 ID，删除已经 covered 的目标；空交集拒绝。
3. 因而 `[r1 missing, r3 covered]` 可变成 `[r1]`；`[r1 missing, r9 unknown]` 整条拒绝，不能用交集掩盖非法 ID。
4. 只有保留任务才计入查询去重集合；每批最多 2 条、原有策略循环/进度与无进展退出保持不变。解析后仍无合法任务时维持 partial/已有终止机制，不制造新查询或偷偷重试。
5. 不替换封存 requirements，不更改 covered 的原文支持要求，不把补查查询当成证据。

共享入口供 P&E replan 与 MA follow-up 使用。Workflow 本轮只统一初始规划及评估提示，**不新增 Workflow 补查循环**。

## 兼容性与代码边界

`ResearchRequirement`、ResearchOutcome / TopicOutcome、checkpoint 格式和 evidence_contract_version=2 保持不变；execution_constraints 不新增至持久化状态或对外结果，原始任务已有权威约束。

新运行使用新规划提示；恢复既有 v2 中间态不重写已封存要求。如果旧规划把过程约束封存为 requirement，其原有缺口可能继续存在，这是保留执行语义的取舍，不静默迁移。已完成旧记录仍按既有方式读取。

拟改：共享规划/解析辅助结构，三模式初始规划节点，共享 evaluator 指令，`parse_gap_tasks` 及调用者；对应 requirements/progress、三模式集成与引用/恢复回归。已有 evidence_evaluation.py 较大，规划专用代码放到小型 planning.py，不把无关 evaluator 重构混入此轮。

## 验证与真实 API 边界

先 TDD 复现混合目标误丢弃及未知 ID/纯已覆盖目标保护；验证分区输出不把 execution_constraints 加入事实 requirements，完整任务及全部用户约束仍进入下游上下文。测试真实三模式节点、封存要求不可被补查重写、checkpoint 往返、缺少原文支持仍不能 completed。

完成相关回归后运行全后端非真实 API 测试、隔离评测测试及改动文件 lint/format；修复无关旧 lint 不在范围。代码修改前后分别保存实验身份，不覆盖上一批数据。

真实复测沿用用户既有真实 API 授权，但另登记新批次：同三道 dev 题 × 三模式，repeat=1，Answer 上限 2000，长期记忆关闭，同 doubao-seed-2.0-lite、temperature=0、本地冻结资料、输出 4096、40 逻辑调用 / 80 Provider 尝试 / 24 工具入口 / 12 分支轮 / 360 秒；整批 360 逻辑 / 720 Provider 上限。仅改变本轮实现，不把高预算探针条件混入。Ragas 主评分最多 144 次，评分模型和配置不变。

baseline 代码/输入/模型未改；本轮不新跑基线，也不与旧基线作新的同条件因果对比。与上一轮同三模式开发诊断分开对照，披露样本小、无重复运行、Provider 非确定性、前轮到本轮同时包含先前异常分类修复；不能把全部差异归因本轮规划优化。

禁止自动换新目录重试整个批次或重复裁判取最高分。失败、partial、N/A 均保留。主指标需要同时报告完成数和语义覆盖，不能只报有答案样本的高分。本轮不承诺 completed 或可靠生产联网 E2E 已通过。

## 自检与流程状态

已核对范围、边界、兼容、测试与有界付费验证；无待定参数。仅第一轮规划/补查，循环及评估紧凑化另作下一份规格。用户已批准分步方向；书面规格待审阅后才进入 implementation plan 与代码修改。

- [x] 项目/轨迹/近期改动调查，实际最小输入复现补查误丢弃。
- [x] 视觉辅助适用性判断：本次为契约文字与规则，无需开启。
- [x] 用户确认分步范围与优先级。
- [x] 比较仅改提示、共享契约+校验及重做状态机方案。
- [x] 呈现首轮设计与书面规格、完成规格自检。
- [ ] 用户审阅书面规格。
- [ ] 调用 writing-plans，进入实施。
