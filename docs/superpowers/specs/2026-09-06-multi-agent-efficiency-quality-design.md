# Multi-Agent 效率与质量优化设计

日期：2026-09-06

状态：方向已由用户确认，等待书面规格复核后实施。

## 1. 问题与目标

运行 `7867aea35c1e` 用 499.9 秒、78,259 Token，只读取成功 6 个页面并以 partial 结束。Researcher 消耗 62,073 Token，占 79.3%；Supervisor 两次决策均先失败，累计 174.9 秒；Writer 用时 119.7 秒。27 个逻辑工具调用中有 19 次搜索、8 次抓取，最终只有 6 个成功抓取。第二次 Supervisor 决策修复后仍无效，预留的 6 次补查额度没有使用。

本轮目标是修正执行策略，而非增加总额度：

- 减少纯搜索扇出，让网络额度优先形成可引用原文。
- 限制进入 Researcher 的工具结果体积，不增加 LLM 笔记层。
- 让 Supervisor 失败原因可诊断，降级时保留真实任务缺口。
- 让前端事件准确区分排队与实际执行。
- 提高一手来源和用户时间范围的优先级。
- 保持 Basic、Deep 以及共用 Writer 的外部契约不变。

时间、Token 和费用继续只统计，不作为整次运行停止条件。仍使用研究员数、模型决策轮数、网络工具调用数和单次请求超时约束执行。

## 2. 方案比较

### 2.1 只改提示词

要求模型少搜索、早读取、优先官方来源。改动最小，但运行已经证明模型会在每轮并行发起三个搜索，提示词不足以形成成本上界，因此不采用。

### 2.2 受约束的 Multi-Agent，推荐

保留 Supervisor 与独立 ReAct Researcher，但由程序控制每轮可见工具、工具批量和返回体积。模型仍选择研究方向和是否完成，程序保证一次决策不会扩张成三组重复搜索。这保留 Agent 特征，同时让成本和收尾可预测。

### 2.3 将每个 Researcher 改成固定搜索工作流

速度最可控，但会退化为并行 Basic，失去根据资料反馈调整方向的能力，不符合新增高级 Agent 模式的定位，因此不采用。

## 3. Researcher 执行协议

默认每个 Researcher 使用三次模型决策：两次研究决策和一次只收尾决策。提前完成仍立即退出，不补一次额外总结。

研究决策只向模型暴露：

- `research_topic`：一次搜索并读取 1 至 3 个候选页面，作为主要工具。
- `fetch_page`：读取用户输入、记忆或上一轮返回的已知 URL。
- `search_memory`：本地历史页面检索。
- `finish_research`：当前任务已经足够时结束。

`search_web` 保留为工具层内部能力和可测试接口，但不再直接暴露给 Researcher 模型。这样避免一次响应生成三个纯搜索而不读取原文。

每个研究决策最多执行一个研究工具。若 Provider 返回多个研究工具调用，程序按返回顺序选择第一个合法调用，并产生 `tool.batch_limited` 事件，其他调用不执行、不扣网络额度。若响应同时包含 `finish_research` 与研究工具，则视为无效决策，不执行工具。

第一轮提示建立代表性资料基础，优先 `research_topic`。第二轮提示只补当前必需交付中的关键缺口；已有足够原文时必须结束。最后一轮只绑定 `finish_research`，沿用保守收尾语义。

默认 `multi_agent_max_researcher_rounds` 从 4 改为 3。环境变量显式配置仍优先，但最小值保持 2，允许一轮研究加一轮收尾。

## 4. 工具结果与上下文边界

搜索摘要只是导航信息：

- 每次最多返回前三个候选。
- 标题最多 200 字符。
- 每个摘要最多 300 字符。

抓取后继续用现有 BGE 选择相关原文，不调用 LLM 压缩：

- 返回给 Researcher 的决策片段最多 1,200 字符。
- 运行资源层为 Writer 保存每来源最多 3,000 字符的 BGE 原文。
- Writer 总研究上下文最多 30,000 字符，按纳入来源公平分配，`sources` 必须与实际 context 一致。

Researcher 最后只保留两轮完整模型/工具交互；因为研究轮数降为两轮，收尾仍能看到本任务全部研究观察。任务摘要只供 Supervisor 协调，不成为 Writer 的事实输入。不会新增 ResearchNote、Claim、Evidence、Verifier 或逐页 LLM 摘要。

## 5. Supervisor 可靠性

保持普通工具绑定，不设置强制 `tool_choice`。每次结构无效仍最多修复一次。

`supervisor.retry` 增加不含 Provider 原文的 `reason_code`：

- `provider_timeout`
- `missing_tool_call`
- `multiple_tool_calls`
- `invalid_arguments`
- `dispatch_not_allowed`
- `invalid_parent`
- `batch_too_large`

修复后仍失败时：

- 没有任何任务历史：结束为 insufficient，缺口说明主管无法形成有效初始分工。
- 已有任务历史：聚合所有 partial/blocked Researcher 的具体 gaps，去重后作为最终缺口；没有具体缺口时才使用主管决策失败的兜底说明。

降级不根据“有几个来源”推断 completed，也不虚构补查结果。首版不在 Supervisor 失败后用确定性程序自动创建新研究任务，因为程序无法可靠判断哪些语义缺口最重要。

本轮不新增不同 Provider 凭据，也不自动切换模型。模型名称仍来自现有配置；验证记录会明确当前 Provider/模型的结构成功率与耗时，后续可单独设计按角色模型路由。

## 6. 并发与事件语义

默认 `multi_agent_concurrency` 从 2 改为 3，与默认批次大小一致，使三个独立首批任务可同时获得执行机会。环境变量可降回 1 或 2，以适应 Provider 并发限制。

事件改为：

```text
researcher.queued     已创建任务并等待并发槽
researcher.started    已获得并发槽，开始模型/工具执行
researcher.completed  已释放额度并交付结果
```

额度不足以完成一次搜索和一次抓取的任务仍产生 queued、started、quota.reached、completed，不能静默消失。每个事件继续携带 task_id、父任务、局部额度和停止原因。

## 7. 来源与时间范围

Supervisor 将每项任务限制为一个可在局部额度内完成的主题，不再把“技术突破、学术会议、全部模型发布”等多个大范围目标塞给同一 Researcher。`required_outputs` 最多三个，并要求是有限交付，不要求凭空穷举。

Researcher 提示明确：

- 优先官方公告、监管机构、论文或主要当事方材料。
- 聚合页只用于发现线索；存在一手来源时不能只引用聚合页。
- 从用户问题抽取出的年份是硬范围，范围外材料只能用于背景，不能作为当期事件写入交付。
- 来源不足时返回具体 gap，不用低质量文章填满清单。

Writer 提示同步强调时间范围与一手来源，不得将范围外事件写成目标年份事件。由于页面发布时间元数据可能缺失，首版不做会误删有效页面的硬编码年份过滤；通过搜索方向、任务交付和 Writer 三层约束降低越界内容。

## 8. 配置与兼容性

修改 Multi-Agent 默认值：

| 配置 | 旧默认 | 新默认 |
| --- | ---: | ---: |
| `MULTI_AGENT_CONCURRENCY` | 2 | 3 |
| `MULTI_AGENT_MAX_RESEARCHER_ROUNDS` | 4 | 3 |

全局网络额度仍为 30，单 Researcher 上限仍为 10，首批补查预留仍为 20%，Supervisor 轮数仍为 3。用户现有 `.env` 中显式值不自动覆盖或删除；`.env.example` 和文档更新为新默认值。

API mode、AgentResult、运行 JSON 和角色 Token 统计结构不变。新增事件类型和 retry 详情对旧前端/旧记录向后兼容。

## 9. 测试与验收

测试使用脚本模型和本地假工具，不调用真实 Provider：

- 模型一次请求三个搜索时，最多执行一个合法研究工具并产生批量限制事件。
- Researcher 模型绑定中不再出现 `search_web`；工具层仍可独立测试该接口。
- 两次研究决策后的最后工具结果完整进入收尾，提前 finish 不增加调用。
- 搜索结果数量、摘要长度、Researcher 页面片段和 Writer 上下文都有硬上界。
- Supervisor retry 记录具体 reason_code；两次失败后聚合已有 Researcher gaps。
- 三个任务在并发 2 时第三个先 queued、获得槽后才 started；并发 3 时三者可同时执行。
- 一项任务失败或额度不足不取消同批其他任务，所有租约归还。
- 提示与脚本行为覆盖一手来源优先和年份范围，Writer 原有数字标题、引用及文末 URL 测试继续通过。
- 全量 Basic、Deep、Multi-Agent 测试、Ruff、compileall、锁文件检查全部通过。

自动化通过后重启本地后端。真实 Provider 对比会产生费用，因此只在用户明确要求后运行。对比同一问题和 30 次网络额度，记录成功抓取数、搜索/抓取比例、Supervisor 结构成功率、角色 Token、墙钟时间、来源质量和报告时间范围；不预先承诺固定降幅。

## 10. 范围外事项

- 不修改 Basic 或 Deep 的执行策略。
- 不引入新的 Agent 框架和第三方依赖。
- 不增加运行总时间、累计 Token 或费用停止预算。
- 不实现自动事实验证、Claim/Evidence 数据模型或逐页 LLM 摘要。
- 不在本轮实现按角色 Provider、API Key、Base URL 或模型自动路由。

## 11. 设计自检

- [x] 没有用增大轮数或额度掩盖执行策略问题。
- [x] Token 优化不依赖恢复 ResearchNote 或 LLM 压缩。
- [x] 工具、Supervisor、并发事件和 Writer 的输入边界一致。
- [x] 默认值、显式环境变量优先级和旧运行记录兼容关系明确。
- [x] 失败降级保留真实缺口，不用状态标签粉饰质量。
- [x] 真实付费验证与自动化验证边界明确。
