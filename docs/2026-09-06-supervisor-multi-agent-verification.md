# Supervisor Multi-Agent 验证记录

日期：2026-09-06

## 结论

第三种 `multi_agent` 模式已按平级目录实现。顶层由 LangGraph 编译为 `START → plan → execute → replan → execute/replan 循环 → writer → END`，每个 execute 节点并发运行多个隔离的 ReAct Researcher。它没有替换或调用 Basic、Deep 的流程代码，只共享 Writer、模型、观测、搜索抓取、BGE 上下文筛选、记忆与配置等基础能力。

自动化验证覆盖主管决策、独立 Researcher、受限收尾、批次并发、额度预留与归还、失败隔离、单飞缓存、原文到 Writer 的来源一致性、API/CLI 路由和前端模式入口。时间、Token 与费用仍只统计，不参与停止；研究停止由循环次数、研究员数量和网络工具调用额度控制。

## 已验证行为

- Supervisor 使用普通工具绑定，不传强制 `tool_choice`；无效结构最多修复一次，最后一轮只能结束。
- 首批任务能限并发执行。单个 Researcher 达到额度或 Provider 失败，不会取消同批其他任务。
- 每个 Researcher 有独立消息、已知 URL、已读来源和本地额度；只有实际读取的 URL 能进入任务交付。
- 每任务最后一次模型决策专用于结构化收尾，不再调用研究工具；收尾无效时有原文返回 partial、无原文返回 blocked。
- 同查询和同 URL 的并发请求使用单飞；同步 Tavily 调用移到工作线程，不阻塞异步调度。
- 实际网络搜索和抓取才扣额度，失败也扣；运行内缓存与本地记忆查询不重复扣网络额度。
- 首批预留 20% 全局网络额度用于定向补查；未使用租约会归还，额度不足的任务产生可见 blocked 事件。
- Writer 只接收任务实际引用的 BGE 筛选原文，且截断后的 context 与 sources 保持一致；任务摘要不作为事实材料。
- `UsageBreakdown` 独立统计 Supervisor、Researcher、Writer，用量汇总不重复；Writer 耗时也进入分角色统计。
- Basic 仍为默认模式，Deep 路由保持原含义，未知 mode 被拒绝。

## LangGraph 重构与提前结束修正

- 持久任务表保留初始任务和补查任务的稳定 ID、父子关系、状态、任务摘要与具体缺口；重规划只追加任务，不覆盖尚未执行或已经完成的任务。
- 最终未解决问题只从当前叶子任务计算。子任务执行后才替代父任务缺口；部分完成的子任务会继续暴露自己的新缺口。
- 当叶子缺口、研究员名额、至少两次网络额度和后续主管轮次同时存在时，Supervisor 的结束决策即使声称充分也会被拒绝，并按每个未解决叶子任务生成一个定向补查任务。
- Supervisor 超时只发起一次 Provider 调用，随后打开运行内熔断；后续重规划使用确定性缺口计划，不再连续等待相同超时。
- 补查批次未增加任何新来源时以 `stagnant` 停止；研究员数量、工具额度和主管轮次分别使用 `researcher_limit`、`global_tool_limit`、`supervisor_round_limit` 标识。
- 应用当前日期和时区作为权威输入传给 Supervisor、Researcher 与 Writer，避免模型用训练截止知识误判当前年份。

## 2026-09-06 效率与质量修正

- Researcher 默认改为两次研究决策加一次只收尾决策；每次决策最多执行一个研究工具，`search_web` 不再暴露给模型。
- 导航搜索最多返回 3 条结果，标题 200 字符、摘要 300 字符；Researcher 每个已读来源最多接收 1,200 字符，Writer 保留每来源最多 3,000 字符，Multi-Agent Writer 总输入最多 30,000 字符。
- 首批默认并发由 2 调整为 3；新增 queued/started 分离，排队任务不再提前显示为已开始。
- Supervisor 结构错误的修复记录只包含清洗后的原因码；Provider 超时不重试，立即按 Researcher 已报告的具体叶子缺口降级，并对后续主管调用熔断。
- Supervisor 任务被限制为一个明确主题和最多 3 个可核对输出；Supervisor、Researcher 与 Writer 都把用户指定年份或日期区间作为硬边界。

诊断基线运行 `7867aea35c1e` 用时 499.9 秒、消耗 78,259 Token，包含 19 次搜索、8 次抓取尝试、6 个成功页面和两次 Supervisor 修复。该数据只用于定位问题；未运行付费对照，因此不宣称真实场景的百分比提升。模型本身的工具调用稳定性和响应速度仍可能主导总耗时。

## 自动化命令

在 `backend` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src\deeptrace tests
uvx ruff check src/deeptrace/multi_agent src/deeptrace/config/settings.py src/deeptrace/prompts/writer.py tests/multi_agent
uv lock --check
.\.venv\Scripts\python.exe -m deeptrace.cli --help
```

全量测试结果为 `196 passed`。Multi-Agent、共享 Writer 与对应测试的 Ruff 检查通过；源码和测试编译、锁文件校验、CLI 三模式枚举及 `git diff --check` 均通过。本次没有把未修改目录纳入全仓库 Ruff 结论。

## 尚未执行

本轮没有自动发起真实 Provider/Tavily 研究，以免在未得到明确授权时产生外部费用。真实对比应使用同一问题、模型和 30 次全局网络额度，记录报告核心覆盖、重复查询、网络尝试、Provider Token 与墙钟耗时；不能只比较 completed 状态。
