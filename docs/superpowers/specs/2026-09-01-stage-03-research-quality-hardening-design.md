# 阶段 3 研究质量加固设计

- 状态：已完成
- 日期：2026-09-01
- 基线：[阶段 3 规划式 Deep Research 设计](2026-09-01-stage-03-planned-deep-research-design.md)
- 后续阶段：阶段 4 Evidence Store 与 Verifier

实现验收于 2026-09-01 完成：非真实测试 63 项通过，Python 编译检查通过；真实 CLI 使用真实 LLM、Tavily、网页抓取和本地 `D:\Dev\Models\bge-m3` 跑通到 Writer。真实运行中两个任务取得时间有效笔记，后续任务因 600 秒全局时间预算停止并诚实返回 `partial`，CLI 正确输出抓取/时间分类和按角色 Provider Token。阶段 4 范围未提前实现。

## 1. 背景

阶段 3 已跑通 Planner、Researcher、真实搜索与抓取、本地 BGE-M3 召回、ResearchNote 压缩和 Writer 报告链路。真实测试同时暴露出以下质量缺口：

- 研究计划包含时间范围，但搜索、抓取、压缩和覆盖判断没有贯通该范围。
- 后发综述与后发事件没有区分，2025、2026 年的新产品可能被写成 2024 年进展。
- 来源数量可以让覆盖状态提升，但来源类型、时间适配和域名多样性没有参与判断。
- 子任务串行消耗共享 Token 预算，前序任务可能让后续任务没有执行机会。
- Writer 可能不遵循用户语言，且来源列表无法说明哪些是当期材料、哪些是后发回顾。
- CLI 只显示工具数和新增笔记数，无法解释抓取、时间过滤或压缩失败。
- 阶段 2 Token 指标与阶段 3 Provider usage 没有统一，出现压缩次数和角色用量显示为零但总用量很高的矛盾。

本次加固修复阶段 3 的输入质量、预算公平性和结果表达，不引入 Claim、Evidence Store、Verifier、Memory、API、Web UI 或评测平台。

## 2. 目标与非目标

### 2.1 目标

- 区分来源发布时间与内容所描述事件的发生时间。
- 允许使用后发综述，但禁止把目标时间外的新事件倒灌进报告。
- 优先抓取一手、学术和高质量二手来源，同时保留可解释降级路径。
- 只让时间有效、来源可接受的 ResearchNote 参与覆盖和写作。
- 为每个计划任务保留合理研究预算，并为 Writer 预留 Token。
- 强制报告语言跟随用户问题，明确披露后发回顾、未知时间和覆盖缺口。
- 让 CLI 能解释候选、抓取、时间判断、压缩和预算结果。
- 保持现有阶段 3 角色边界和六节点 LangGraph 主拓扑。

### 2.2 非目标

- 不把 ResearchNote 拆成 Claim。
- 不建立持久化 Evidence Store。
- 不判断事实真假，不解决来源之间的事实冲突。
- 不提供 Claim 级引用覆盖率或 Verifier 结论。
- 不以固定域名白名单宣称来源可信。
- 不通过简单发布日期上限删除所有后发资料。
- 不进行大规模基准、消融或开源项目对比。

## 3. 核心时间语义

系统同时处理两个时间：

- `source_published_at`：页面、论文或报告的发布时间。
- 事件时间：ResearchNote 中保留的信息实际描述哪个时期发生的事件。

时间适配状态定义为：

```python
TemporalRelation = Literal[
    "in_range",
    "retrospective",
    "out_of_range",
    "unknown",
    "not_applicable",
]
```

- `in_range`：笔记描述目标时间范围内事件，来源也在该范围内发布。
- `retrospective`：来源在目标范围之后发布，但笔记明确回顾目标范围内事件。
- `out_of_range`：笔记主要描述目标范围之外发生的新事件。
- `unknown`：无法可靠确定事件时间或无法隔离混合年份内容。
- `not_applicable`：用户问题没有时间范围。

后发综述可以正常使用。Writer 必须把其中的后续评价写成“后续研究或回顾认为”，不能表达成目标年份当时已经形成的判断。

对于同时包含多个年份的页面，压缩器只保留目标范围相关的 key points 和 evidence snippets。无法隔离时不产出关键笔记，记录 `unknown` 或 `out_of_range` 诊断。

## 4. 数据模型调整

### 4.1 RawDocument

`RawDocument` 增加可选来源元数据：

```python
source_published_at: datetime | None = None
source_modified_at: datetime | None = None
publisher: str | None = None
```

抓取器按以下优先级提取日期：

1. JSON-LD 的 `datePublished`、`dateModified`。
2. OpenGraph 或 article metadata。
3. `<time datetime>` 和常见确定性 meta 字段。
4. 无法可靠解析时保留 `None`。

不得把抓取时间当成发布时间，也不得仅凭页面正文中任意年份确定发布时间。

### 4.2 ResearchNote

`ResearchNote` 增加：

```python
source_published_at: datetime | None = None
event_start_date: date | None = None
event_end_date: date | None = None
source_kind: Literal[
    "official",
    "academic",
    "reputable_secondary",
    "other",
    "unknown",
] = "unknown"
temporal_relation: TemporalRelation = "not_applicable"
temporal_scope: str = ""
```

`temporal_scope` 只解释时间关系，不充当 Claim。例如：

> 来源发布于 2026 年，本笔记仅保留其对 2024 年框架发布与采用情况的回顾。

`event_start_date`、`event_end_date` 表示该任务级笔记保留内容的总体事件范围。压缩器必须先移除目标期外 key points；剩余内容无法用一个总体范围表达时使用 `None` 并将关系标记为 `unknown`，不在阶段 3 拆分为 Claim。

本地规范化优先于模型标签：

- 问题无时间范围时固定为 `not_applicable`。
- 事件范围与目标范围不相交时固定为 `out_of_range`。
- 事件范围落在目标范围内，且来源发布晚于目标结束日时为 `retrospective`。
- 事件范围落在目标范围内，来源也在范围内时为 `in_range`。
- 缺少足够日期或出现矛盾时为 `unknown`。

来源类型是阶段 3 排序提示，不代表事实已验证。`academic` 需要论文仓库、DOI、期刊或会议元数据；`official` 需要页面 publisher 与负责该产品、研究或政策的组织一致；`reputable_secondary` 需要可识别出版机构、作者或编辑信息及明确发布日期。其余使用 `other` 或 `unknown`。分类失败不能阻断整轮研究。

### 4.3 覆盖状态

TaskCoverage 增加可解释计数：

```python
valid_note_ids: list[str]
retrospective_note_ids: list[str]
unknown_time_note_ids: list[str]
out_of_range_note_ids: list[str]
qualified_source_urls: list[str]
```

旧字段继续保留，避免破坏现有状态序列化和 Writer 输入。

## 5. 检索与来源选择

### 5.1 三类查询意图

每个任务的查询覆盖：

1. 当期一手来源：目标年份、产品或研究名称、官方公告或原始论文意图。
2. 后发回顾来源：目标年份与 retrospective、review、年度回顾等意图。
3. 缺口补充：Researcher 根据未覆盖主题动态生成。

Planner 仍最多生成三条计划查询。Researcher 负责在执行时区分意图，不增加无界查询扩展。

### 5.2 候选排序

Tavily 不按发布日期硬截断。候选采用确定性优先级组合：

- Tavily 相关度。
- 标题和摘要对目标年份、任务主题的匹配。
- 官方站点、原始论文、政府或标准机构等来源特征。
- 域名多样性。
- Top、Best、榜单、聚合页等弱来源特征降权。
- 同一域名的重复结果降权。

抓取前的来源判断只能用于排序。抓取和压缩后才能形成最终 `source_kind` 与 `temporal_relation`。

### 5.3 渐进式抓取

每轮先搜索 5 至 8 个候选，只抓取并压缩前 2 至 3 个。覆盖不足时才处理下一批。单个任务默认不让同一域名贡献超过两个候选抓取位。

目标是尽早获得少量高适配笔记，而不是最大化抓取页数。

## 6. 压缩与时间质量门

压缩提示词接收：

- 用户原问题。
- 当前 ResearchTask。
- ResearchPlan.time_range。
- RawDocument 来源时间和 publisher。
- 召回片段。

压缩输出除原有字段外，还返回 `event_start_date`、`event_end_date`、`source_kind`、`temporal_relation` 和 `temporal_scope`。本地先做 Pydantic 校验，再依据计划范围和日期执行时间关系规范化。解析失败时重试一次；仍失败沿用现有压缩失败路径，不伪造笔记。

笔记进入覆盖与 Writer 的规则：

- `in_range`、`retrospective`：有效。
- `out_of_range`：保留诊断，不计覆盖，不交给 Writer。
- `unknown`：可辅助 Writer 披露缺口，不能成为关键进展的唯一依据。
- `not_applicable`：无时间范围问题按现有相关性逻辑处理。

## 7. 来源质量与覆盖判断

任务达到 `sufficient` 必须同时满足：

- 达到 `min_sources` 个不同规范化来源 URL。
- 至少两个不同注册域名或组织来源；同域名多个页面不重复增加多样性。
- 至少存在一条 `official`、`academic` 或 `reputable_secondary` 有效笔记。
- 关键 expected topics 没有未解决缺口。
- 有时间范围时，关键覆盖来自 `in_range` 或 `retrospective`。

`unknown` 和 `other` 可以补充内容，但不能单独把任务提升为 `sufficient`。来源质量不足时保持 `partial`，不得为了完成状态降低门槛。

该覆盖仍是流程质量判断，不是 Claim 级事实验证。

## 8. Token 预算公平性

总 Provider Token 预算分为目标区间：

- Planner 约 5%。
- Writer 预留约 15%。
- Researcher 与 Compression 约 80%。

Planner 完成后使用实际 Planner usage 计算剩余研究池。Writer 预留从研究池中隔离，研究任务不能消耗。

每个任务开始时计算：

```text
当前任务可用研究额度 = 剩余研究池 / 剩余任务数
```

任务未用完额度回流后续任务。达到任务额度时以 `task_token_budget` 部分完成，不再发起新压缩批次。

压缩前通过本地 TokenEstimator 估算本批输入，动态减少页面数。已经开始的 Provider 调用不强制中断，因此总用量仍可能小幅超过阈值；CLI 必须区分研究停止阈值与最终总用量。

预算策略保持子任务串行执行，但保证在全局预算正常的情况下，每个计划任务至少获得一次研究机会。

## 9. Writer 约束

系统根据原始问题确定性选择主要语言，Planner 输出只作为辅助：

- 存在足够中文字符时固定为 `zh-CN`。
- 主要为英文时固定为 `en`。
- 无法判断时才采用 Planner.language。

Writer 只接收有效笔记及必要的 `unknown` 缺口说明。报告必须：

- 使用 plan.language。
- 明确目标时间范围。
- 区分当期事实与后发回顾。
- 标记 partial、failed、missing topics。
- 来源列表按一手或学术、后发回顾、其他来源分组。
- 没有有效笔记时拒绝生成事实性结论。
- 继续声明阶段 3 未做 Claim 级验证。

输出后运行两项轻量校验：

1. 语言一致性：中文问题输出英文时纠正重试一次。
2. 时间表达：正文出现范围外年份且缺少“后续、回顾、截至”等关系说明时纠正重试一次。

两次仍失败时使用确定性有限结论报告。该检查只处理表达和范围，不判断事实真假。

## 10. 可观察性

工具事件从“调用数和新增笔记数”扩展为：

- 搜索候选数。
- 抓取成功、失败和跳过数。
- 抓取失败码聚合。
- 新增 `in_range`、`retrospective`、`unknown`、`out_of_range` 笔记数。
- 当前任务研究 Token 与额度。
- 任务停止的明确原因。

Token 输出按角色汇总：

- Planner。
- Researcher。
- Compression。
- Writer。
- 总 Provider usage。

阶段 2 的上下文压缩指标继续保留，但不能把阶段 3 角色用量错误显示为零。BGE-M3 tokenizer 超长输入在分块前以明确诊断处理，不输出误导性的模型索引警告。

## 11. 错误与降级策略

- 发布时间提取失败：保留 `None`，不直接丢弃页面。
- 来源分类失败：使用 `unknown` 并降权。
- 时间关系失败：使用 `unknown`，不作为关键结论唯一依据。
- 页面包含目标期外新事件：标记 `out_of_range`，不计覆盖。
- 高质量来源不足：章节保持 partial。
- 某个来源失败：继续处理同批其他候选，并聚合真实失败码。
- Writer 语言或时间表达校验失败：纠正重试一次后确定性降级。
- 外部服务失败：真实冒烟不以 Fake、静态内容或手工报告代替。

## 12. 测试与验收

### 12.1 必要自动测试

- JSON-LD、OpenGraph、`time` 标签日期提取及缺失日期。
- 2026 年综述回顾 2024 年事件时标记 `retrospective` 并计入覆盖。
- 2026 年新产品发布在 2024 年问题中标记 `out_of_range` 且不计覆盖。
- 混合年份页面只保留目标期片段；无法隔离时为 `unknown`。
- 无时间范围问题使用 `not_applicable`，不受时间门误伤。
- 同域名多个页面不重复满足来源多样性。
- 只有 `unknown` 或 `other` 来源时不能达到 sufficient。
- 中文问题确定性生成 zh-CN 计划和报告。
- 语言校验与时间表达校验各只重试一次。
- 任务额度耗尽不会阻止后续任务获得研究机会。
- Writer 预留不被前序研究消耗。
- CLI 聚合展示抓取和时间过滤失败原因。
- Provider usage 按四个角色及总计正确累加。

单元测试可以使用受控模型消息和 HTTP 响应验证内部边界，但不能作为真实外部验收结果。

### 12.2 真实端到端冒烟

继续使用：

```powershell
uv run deeptrace "2024年AI Agent领域有哪些重要进展？"
```

必须使用真实 LLM、Tavily、网页抓取和本地 `D:\Dev\Models\bge-m3`。验收要求：

- 至少两个研究任务实际执行并获得有效笔记。
- 后发综述可以进入，但明确标记为 retrospective。
- OpenAI Presence、Microsoft Agent Framework 等目标期外新事件不得写成 2024 年进展。
- 至少一个章节使用官方、学术或高质量二手来源。
- 中文问题生成中文报告。
- 所有计划任务在预算允许时至少获得一次研究机会。
- partial 状态如实展示缺口和停止原因。
- CLI 显示各角色 Token、抓取失败与时间过滤摘要。
- 无未处理异常，不使用 Fake 外部结果。

只运行本设计涉及的定向测试、现有非真实套件和一次真实冒烟，不做额外大规模评测。

## 13. 阶段 4 边界

阶段 3 加固后的 ResearchNote 仍是压缩后的任务级研究材料。`source_kind` 和 `temporal_relation` 只是检索与写作质量元数据。

阶段 4 再负责：

- 从笔记抽取 Claim。
- 建立 Evidence Store。
- 形成 Claim 与证据片段的显式关系。
- 判断支持、反驳、冲突和证据不足。
- 进行 Claim 级事实、时间和引用验证。

因此，本次加固减少明显错误进入 Writer，但不宣称报告已经事实验证。
