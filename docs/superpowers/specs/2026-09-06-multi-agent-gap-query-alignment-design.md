# Multi-Agent 缺口与查询对齐设计

## 1. 目标

修复 Multi-Agent 研究流程中“Supervisor 已识别具体缺口，但补查任务和 Researcher 查询重新退化为宽泛主题”的问题。补查阶段必须保持从父任务缺口到子任务检查项、研究动作和工具查询的可追踪关系，在不增加新的 Agent 角色和 Writer 调用的前提下，提高资料命中率并减少重复宽搜。

## 2. 问题边界

当前 `ResearchAssignment` 已包含 `objective`、`required_outputs` 和 `parent_ids`，但运行时只验证父任务 ID 是否有效，没有验证补查任务是否覆盖父任务的未解决缺口。Researcher 的工具调用只包含自由文本 `query`，没有说明本次查询服务于哪个检查项。默认三次 Researcher 决策中，前两次可调用研究工具，最后一次只能收尾；具体缺口可能到收尾时才被总结出来，系统因而无法继续定向搜索。

本次只修改 Multi-Agent 模式，不改变 Basic 和 Deep 的流程，不增加时间预算、Token 预算、Critic、Verifier、Claim、Evidence 或 `ResearchNote`。

## 3. 核心设计

### 3.1 补查任务按叶子缺口确定性生成

Supervisor 继续判断哪些缺口值得补查和可使用的研究员数量，但不能通过宽泛改写丢失父任务的叶子缺口。

- 每个补查任务只负责一个具体叶子缺口。
- `required_outputs` 必须保留该缺口的完整语义，不使用“整理完成某方向”替代具体要求。
- `objective` 由程序根据具体缺口生成，格式为“补充并核实：{gap}”。
- `parent_ids` 必须只指向产生该缺口的已执行叶子任务。
- 同一父任务存在多个缺口且容量允许时，拆成多个可并行子任务；容量不足时按原顺序选取，未派发缺口继续保留在任务账本中。
- Supervisor 返回的补查建议只用于选择或排序缺口；最终写入任务账本的 Assignment 由程序依据父缺口编译，不能直接采用语义未校验的自由文本任务。

当 Supervisor 不可用时，确定性降级也使用相同的“一缺口一任务”规则。

### 3.2 研究动作显式绑定检查项

为 Researcher 使用的研究工具参数增加 `target_output` 字段：

```json
{
  "target_output": "欧盟AI法案2025年具体实施进展和核心政策调整细节未充分获取",
  "query": "EU AI Act 2025 implementation European Commission official",
  "max_pages": 3
}
```

- `target_output` 必须与当前 Assignment 的一个 `required_outputs` 精确匹配。
- Researcher 调用 `research_topic`、`fetch_page` 或 `search_memory` 时都必须声明目标检查项；URL 抓取同样需要说明它服务于哪个检查项。
- 运行时拒绝未知检查项，不执行该工具，也不消耗网络额度，并把允许的检查项返回给 Researcher 修复下一次决策。
- 不采用简单关键词重合率判断 Query，因为中英文同义表达会产生误拒绝；对齐依据是明确的 `target_output` 身份，Query 内容由模型围绕该检查项生成。

`search_web` 仍不暴露给 Researcher 模型，继续由 `research_topic` 负责搜索并读取少量网页。

### 3.3 初始研究与补查采用不同策略

- 初始任务允许第一轮围绕 bounded objective 建立资料基础，但工具调用仍需选择一个具体 `required_output`。
- 补查任务禁止重新执行宽泛主题探索。由于其 Assignment 只有一个具体 `required_output`，第一轮必须直接针对该缺口查询。
- 每轮提示显示尚未确认的检查项，并要求 Researcher 优先选择尚未支持的项目。
- 保持现有“两次研究决策 + 一次强制收尾”默认上限。本次通过提高每次查询的针对性解决问题，不简单放大轮次或工具调用上限。

### 3.4 轻量检查项进度

Researcher 在单次任务内部维护轻量进度，不建立新的证据对象：

- 初始状态：所有 `required_outputs` 为 `unchecked`。
- 某检查项发生成功的研究工具调用后记为 `researched`。
- 最终 `finish_research` 仍由模型依据已读原文判断 `completed` 或 `partial`。
- 进度只用于选择下一步和可观测性，不冒充事实支持，也不替代 Writer 对原文的直接使用。

为了避免把模型生成的新缺口拖到最后才暴露，每个正常研究轮的提示要求先报告当前未确认检查项，再选择工具或结束。若最后一次工具调用后仍有缺口，收尾可以保留为 partial，但不会再把原本明确的补查目标浪费在宽搜上。

### 3.5 可观测事件

研究事件补充以下信息：

- `researcher.started`：显示 objective，并在 details 中以 JSON 字符串保存 `required_outputs`，`parent_ids` 继续使用逗号分隔字符串，保持现有公共事件类型不变。
- `tool.started`：显示 `target_output` 与 Query/URL，details 中保存标量字符串 `target_output`。
- 对齐校验失败：产生 `tool.rejected`，原因码为 `unknown_target_output`，不记录未清洗的 Provider 内容。
- `replanning.completed`：补查任务显示对应的具体缺口，而不是只显示宽泛主题。

运行文件应能够从事件还原“父缺口 → 子任务 → 检查项 → 查询”的映射。

## 4. 数据流

1. Researcher 对初始任务返回具体 `gaps`。
2. LangGraph Replan 节点从未被子任务覆盖的叶子任务收集 gap 记录，同时保留 gap 对应的父任务 ID。
3. Supervisor 评估是否继续以及缺口优先级。
4. 程序将被选择的 gap 编译为一缺口一 Assignment。
5. Researcher 从 Assignment 的 `required_outputs` 选择 `target_output`，生成定向 Query 并调用工具。
6. 运行时验证 `target_output` 后执行工具，记录映射事件。
7. 子任务完成后覆盖对应父缺口；未解决的新叶子缺口进入下一次重规划或按既有硬边界结束。

## 5. 兼容性与错误处理

- 工具参数模型采用新增必填字段，不静默接受缺少 `target_output` 的新模型调用；模型得到一次普通研究决策机会进行修复，仍无效则由现有保守收尾处理。
- API 对外请求和最终报告数据结构不变。
- Writer 输入仍是网页正文或 BGE 筛选原文，不读取 Researcher 摘要作为事实证据。
- 全局和每 Researcher 工具额度只在实际网络尝试时扣除；对齐校验失败不扣额度。
- 现有 Supervisor 轮次、Researcher 数量和停滞判断继续生效。

## 6. 测试要求

必须先写失败测试并确认失败，再实现：

1. 多个父缺口在容量允许时生成多个一缺口补查任务。
2. 补查 Assignment 的 objective、required_outputs 和 parent_ids 保留具体父缺口。
3. Supervisor 提交宽泛补查任务时，程序编译后的任务仍与父缺口精确对齐。
4. Researcher 工具调用缺少或使用未知 `target_output` 时不执行网络工具、不扣额度，并产生 `tool.rejected`。
5. 合法 `target_output` 能执行工具，`tool.started` 记录检查项。
6. 补查 Researcher 的提示明确禁止宽泛重搜；初始任务仍允许建立资料基础。
7. `researcher.started` 和 `replanning.completed` 能展示检查项映射。
8. Multi-Agent 定向测试和全量测试通过，Ruff、编译和 `git diff --check` 通过。

## 7. 非目标

- 不通过增加轮次或工具上限掩盖对齐问题。
- 不增加额外 Supervisor、Researcher、Writer 或 Critic 调用。
- 不在本次实现中优化 Writer 上下文长度或模型价格。
- 不以关键词包含关系作为查询质量的硬校验。
- 不自动运行会产生 Provider 或搜索费用的真实研究任务。
