# DeepTrace 默认 Basic 研究模式设计

- 日期：2026-09-04
- 状态：已确认，待实施
- 参考实现：本地 GPT-Researcher v3.6.1 的 BasicReport 流程

## 1. 目标

把 DeepTrace 的默认研究内核重构为 GPT-Researcher BasicReport 风格的浅层并行流水线，优先获得快速、完整、可运行的基础研究能力。

默认模式只执行一次查询规划、一次并行资料收集和一次最终写作。删除 `ResearchNote` 及所有 Evidence、Claim、Verifier 或证据片段领域对象，不保留面向未来模式的兼容字段和空抽象。

## 2. 范围

本次保留现有 FastAPI、SSE、Web UI、CLI、运行持久化、可选页面 Memory、模型 Provider、搜索与抓取基础设施、Token/费用统计和全局运行期限。

本次只实现默认 Basic 模式，不实现详细报告、递归 Deep Research、多 Agent、人工审核、事实核验或评测平台。后续模式各自设计，不改变本次基础链路。

## 3. 总体流程

```text
用户问题
  ↓
使用原始问题执行一次初始搜索
  ↓
Planner 根据问题和初始结果一次生成搜索查询
  ↓
追加用户原始问题并稳定去重
  ↓
所有查询并行搜索
  ↓
URL 全局去重并有界并发抓取
  ↓
Embedding 筛选相关网页正文
  ↓
格式化为 Source / Title / Content 文本
  ↓
合并为一个研究上下文字符串
  ↓
Writer 一次生成完整 Markdown 报告
```

LangGraph 固定为：

```text
START → plan → parallel_research → writer → END
```

节点之间没有单个研究任务的多轮 Agent 循环，也没有研究完成判断、覆盖率补搜或核验回路。

## 4. 查询规划

Planner 输入包括用户原始问题和初始搜索结果的标题、URL、摘要。默认请求生成 3 条互补且可直接交给搜索引擎的查询；解析失败、模型失败或结果为空时降级为只使用原始问题。

普通路径把原始问题追加到生成查询末尾并稳定去重，因此默认最多执行 4 条查询。Planner 不再生成 `ResearchPlan`、`ResearchTask`、章节 ID、来源类型要求、预期要点或任务 Token 预算。报告结构由 Writer 根据最终上下文决定。

初始搜索只服务于规划。相同原始问题在并行研究阶段出现时允许复用初始结果，避免重复网络请求。

## 5. 并行搜索与抓取

所有查询使用 `asyncio.gather` 同时执行。单条查询完成以下工作：

1. 调用已配置的搜索服务获取候选结果。
2. 复用搜索服务已经返回的完整正文；只有缺少正文的结果进入抓取。
3. 根据规范化 URL 在本次运行内全局去重。
4. 使用共享 Semaphore 限制抓取并发。
5. 单条查询或单个网页失败时记录事件并继续处理其他结果。

并发结果按查询顺序和搜索结果顺序稳定合并。共享 URL 去重必须使用异步锁或等效的原子认领机制，不能依赖并发协程直接读写普通集合产生竞态。

默认参数与 GPT-Researcher BasicReport 对齐：每条查询最多 5 个搜索结果，抓取并发上限 15。根据 2026-09-05 的最新要求，取消总时间、累计 Token 和费用停止条件；默认最多 30 次搜索/网络抓取调用，其中网络抓取最多 20 次。不再给每个子任务分配轮次或预算，时间与 Token 只作统计，单次请求保留故障超时。

## 6. 上下文处理

抓取结果的研究数据只包含页面级字段：

```text
url
title
raw_content
```

页面可以继续由现有 `RawDocument` 承载，以复用抓取、Memory 和持久化基础设施。`DocumentChunk` 不进入 LangGraph State、API 或 Writer 契约；分块只是 Embedding 筛选函数内部的临时值，不定义新的证据片段模型。

上下文处理对齐 GPT-Researcher：

- 全部候选正文少于 8000 字符且页面数不超过返回上限时，跳过 Embedding，直接使用正文。
- 其他情况按 1000 字符切块，相邻块重叠 100 字符。
- 使用现有 Embedding 运行时计算相关性，默认阈值为 0.42。
- 每条查询最多保留 10 个相关结果。
- 筛选结果直接格式化为文本，不生成摘要，不调用压缩 LLM，不保存片段 ID。

标准文本格式为：

```text
Source: https://example.com/page
Title: 页面标题
Content: 与当前查询相关的网页原文
```

各查询的文本结果按规划顺序拼接为单个 `research_context: str`。系统不再维护 `notes`、`note_id`、`used_note_ids`、笔记向量注册表、笔记召回、笔记质量统计或任务覆盖率。

## 7. Writer 与引用

Writer 只接收用户问题、研究上下文、语言和报告配置，一次生成完整 Markdown 报告。Writer 不调用搜索和抓取工具，也不返回结构化的笔记或证据引用 ID。

引用方式对齐 GPT-Researcher：上下文中的 `Source` URL 提供给模型，提示词要求在相关叙述旁生成 Markdown 超链接。报告末尾追加本次成功使用或访问的唯一 URL 列表，顺序稳定。

本次移除引用编号白名单、机械引用拼接、Claim 支撑校验和“只展示 Writer 明确选中来源”的规则。报告不得声称已经完成 Claim 级事实验证。

Writer Provider 调用继续受现有绝对期限保护。首次调用失败时允许一次受同一期限约束的重试；仍失败或超时时，使用确定性降级报告呈现已经取得的上下文和来源。

## 8. 状态与公共接口

LangGraph State 保留：

- 用户问题与搜索查询列表；
- 初始搜索结果和去重后的网页文档；
- 合并后的研究上下文字符串；
- 最终报告和来源 URL；
- 事件、状态、错误、终止原因、耗时、Token 与费用；
- 全局页面数和运行期限所需计数。

删除：

- `ResearchPlan`、`ResearchTask`、`TaskCoverage`、`TaskCompletion`、`SectionResult`；
- `ResearchNote`、`CompressionOutcome` 和笔记相关审计模型；
- Evidence、Claim、Verification 相关模型与字段；
- `used_note_ids` 及所有笔记来源反查接口；
- 任务索引、任务轮次、覆盖率、补搜和逐任务完成状态。

API 和运行记录继续返回最终状态、报告、来源、事件、用量、耗时和终止原因。删除已经失去语义的计划、章节和笔记字段，不为旧内部接口保留兼容壳。

## 9. 事件

默认事件保持用户可理解且与真实并发一致：

- `planning.started`：开始初始搜索与查询规划；
- `planning.completed`：列出最终搜索查询；
- `query.started`：某条查询开始；
- `query.completed`：该查询的搜索、抓取和有效上下文统计；
- `budget.reached`：触发全局页面数、时间或费用限制；
- `research.completed`：全部并行查询收束；
- `writing.completed` 或 `writing.fallback`；
- `run.completed`。

删除会暗示串行任务执行或笔记压缩的 `task.*`、`tools.completed` 和笔记数量文案。

## 10. 错误与终态

- Planner 失败时使用原始问题继续，不让运行失败。
- 单条查询失败不取消其他查询。
- 单页失败不丢弃同一查询下的成功页面。
- 全局期限到达后停止启动新的网络工作，取消仍可安全取消的等待，并使用已有上下文进入 Writer。
- 没有任何有效上下文时不生成看似有来源的报告，返回明确的资料获取失败说明。
- 有非空报告且至少一个来源时为 `completed`；只有降级内容或部分资料时为 `partial`；没有可交付报告时为 `failed`。
- 用户取消保持 `cancelled`，不进入 Writer。

## 11. 测试与验收

自动化测试覆盖：

1. Planner 根据初始搜索结果生成查询，并把原始问题追加、稳定去重。
2. Planner 异常和非法输出降级为原始问题。
3. 多条查询实际并发，而不是按列表串行等待。
4. 并发 URL 认领不会重复抓取同一页面。
5. 小上下文跳过 Embedding，大上下文执行切块和相关性过滤。
6. Writer 输入严格采用 `Source / Title / Content`，不含 `ResearchNote`、Claim 或 Evidence 结构。
7. 空研究上下文拒绝生成虚假报告。
8. Writer 超时进入确定性降级。
9. API、SSE、运行持久化和取消行为保持可用。
10. 源码和当前文档中不再存在运行时 `ResearchNote`、Evidence、Claim、Verifier、`used_note_ids` 或任务级多轮研究入口。

验收执行全部非真实 Provider 测试、编译检查、CLI 帮助检查和 Git 差异检查。自动化测试通过后只进行一次真实 API 端到端研究，确认并行查询事件、非空报告、来源列表、持久化结果和可接受总耗时。

## 12. 文档策略

旧阶段设计和实施计划基于已经放弃的 ResearchNote、任务级多轮研究、Evidence/Claim/Verifier 或机械引用架构，全部删除，不作为当前实现依据。

`docs/q.md` 保留为真实问题和修复记录，其中历史描述只代表当时状态。实现完成时同步重写 `backend/README.md`，使运行说明、环境变量、事件和返回结构与本设计一致。
