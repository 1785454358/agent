# 阶段 4 Evidence Store 与 Verifier 设计

- 状态：设计已确认，待实施
- 日期：2026-09-01
- 基线：[DeepTrace 总体目标架构](../../architecture/deeptrace-target-architecture.md)
- 前置阶段：[阶段 3 研究质量加固](2026-09-01-stage-03-research-quality-hardening-design.md)
- 后续阶段：阶段 5 Memory、持久化、API 与 Web UI

## 1. 背景

阶段 3 已经具备 Planner、逐任务 Researcher、真实搜索与抓取、本地 BGE-M3 召回、ResearchNote 压缩、来源与时间质量过滤、Writer 和运行预算。ResearchNote 仍是任务级材料，`key_points` 与 `evidence_snippets` 之间没有稳定的 Claim 关系，Writer 也只能声明报告基于研究笔记，不能证明某个确定事实由哪段原文支持。

阶段 4 在单次研究运行内建立 `Source → Evidence → Claim → VerificationResult` 数据链，并把验证缺口反馈给 Researcher 做一次有界补搜。目标是让报告中的确定事实能够回溯到真实页面原文，同时诚实保留不支持、冲突、时间越界和预算不足。

## 2. 目标与非目标

### 2.1 目标

- 从真实 `RawDocument` 和有效 `ResearchNote` 构建运行内 Evidence Store。
- 每条 Evidence 保存不可改写摘录和原文字符位置；无法定位的摘录不能支持验证通过。
- 将研究材料拆成原子 Claim，并显式关联 Evidence ID。
- 使用确定性规则与单个真实 LLM Verifier 判断支持、部分支持、不支持、冲突和时间越界。
- 检查重要数字的数值、单位、统计口径和时间基础。
- 将关键证据缺口转换为结构化补搜输入，返回 Researcher，且每个任务最多补搜一次。
- Writer 只把验证通过的 Claim 写成确定事实，并生成 Claim 级引用。
- 在 CLI 和 `AgentResult` 中暴露 Claim、验证、缺口、补搜和按角色 Token 统计。
- 保持所有 Graph State 数据 Pydantic 可序列化，保留阶段 3 的真实搜索、抓取、压缩和预算行为。

### 2.2 非目标

- 不引入 SQLite、PostgreSQL、向量数据库或跨运行 Evidence Store。
- 不实现 Memory、checkpoint、任务恢复、FastAPI、Web UI 或后台任务。
- 不增加第二个裁判模型、多模型投票或人工审核工作流。
- 不接入新的搜索引擎、MCP 或付费来源渠道。
- 不宣称 Verifier 判断等同于客观真理；它只判断当前证据对 Claim 的支持关系和规则完整性。
- 不运行固定数据集、大规模准确率评测、消融或开源项目对比。

## 3. 方案选择

采用逐任务验证闭环：一个 ResearchTask 完成初步研究后，先完成证据入库、Claim 抽取和验证；关键 Claim 有缺口时，当前任务执行一次补搜，再重新入库和验证，之后才进入下一任务。

不采用全部任务结束后统一验证。阶段 3 的真实运行可能在后段触发全局时间预算，统一后置会导致前面已经完成的研究也没有验证结果。逐任务闭环可以让已完成章节在部分运行中仍保留可用验证结论。

不在 Writer 内执行验证。Writer 只负责组织已判定结果，不能同时承担检索、事实判断或证据存储。

## 4. 总体流程

```text
Planner
  ↓
start_task → Researcher ←→ search / fetch / compress
  ↓
complete_task（生成 provisional SectionResult，不推进任务索引）
  ↓
evidence_ingest
  ↓
claim_extract
  ↓
verify
  ├── 有关键缺口、未补搜且预算允许
  │       ↓
  │   verification_research ←→ search / fetch / compress
  │       ↓
  │   evidence_ingest → claim_extract → verify
  └── 无需或不能继续补搜
          ↓
      finalize_task（固化章节并推进任务索引）
          ↓
      下一任务 / Writer
```

每个任务最多进入一次 `verification_research`。一次补搜最多处理两个高优先级缺口、执行两个搜索查询并新增抓取三个页面。第二次验证后无条件进入 `finalize_task`；仍有缺口时保留结构化原因。

## 5. 数据模型

所有模型放在 `models/`，使用 Pydantic 2，并保持 JSON 可序列化。稳定 ID 由本地哈希生成，不接受模型自由生成的 ID。

### 5.1 Source

```python
class Source(BaseModel):
    source_id: str
    doc_id: str
    channel: Literal["web"] = "web"
    requested_url: str
    final_url: str
    canonical_url: str | None
    title: str
    publisher: str | None
    source_kind: SourceKind
    publication_date: datetime | None
    modified_date: datetime | None
    fetched_at: datetime
    scraper_used: ScraperUsed
    content_hash: str
```

一个 `doc_id` 对应一个 Source。`publication_date` 只表示来源发布时间，不代替事件时间。阶段 4 只支持真实 Web 页面，但保留 `channel` 字段供后续扩展，不提前接入其他渠道。

同一文档被多个任务重复压缩时只 upsert 一个 Source。若 ResearchNote 对同一文档给出不同 `source_kind`，入库结果固定降为 `unknown` 并记录 `source_kind_conflict`，不得选择其中更强的分类来提升验证状态。

### 5.2 Evidence

```python
EvidenceLocationStatus = Literal["exact", "unlocated"]

class Evidence(BaseModel):
    evidence_id: str
    source_id: str
    doc_id: str
    note_id: str
    task_id: str
    section_id: str
    quote: str
    quote_hash: str
    char_start: int | None
    char_end: int | None
    location_status: EvidenceLocationStatus
    event_start_date: date | None
    event_end_date: date | None
    temporal_relation: TemporalRelation
```

Evidence 的 `quote` 必须逐字来自 `RawDocument.content`。入库服务使用精确子串匹配定位字符区间；重复摘录固定使用第一次出现的位置。无法精确匹配时保存为 `unlocated` 供诊断，但它不能进入支持证据集合。`evidence_id` 由 `source_id + note_id + quote_hash + char_start` 生成。

### 5.3 Claim

```python
ClaimKind = Literal["factual", "numeric", "comparative", "temporal"]
ClaimImportance = Literal["key", "supporting"]

class NumericDetail(BaseModel):
    value_text: str
    unit: str | None
    scope: str | None
    time_basis: str | None

class Claim(BaseModel):
    claim_id: str
    task_id: str
    section_id: str
    text: str
    kind: ClaimKind
    importance: ClaimImportance
    event_start_date: date | None
    event_end_date: date | None
    numeric: NumericDetail | None
    evidence_ids: list[str]
```

Claim 必须表达一个可独立判断的事实。复合句由 Claim Extractor 拆分。`claim_id` 由规范化 Claim 文本、任务和章节生成；重复抽取执行 upsert。模型只能引用输入中存在的 Evidence ID，本地代码删除未知 ID。

### 5.4 VerificationResult 与 Gap

```python
VerificationVerdict = Literal[
    "verified",
    "partially_supported",
    "unsupported",
    "conflicted",
    "out_of_range",
]

class VerificationIssue(BaseModel):
    code: str
    severity: Literal["warning", "blocking"]
    message: str

class EvidenceAssessment(BaseModel):
    evidence_id: str
    relation: Literal["supports", "refutes", "unrelated"]
    reason: str

class VerificationResult(BaseModel):
    claim_id: str
    verdict: VerificationVerdict
    reason: str
    supporting_evidence_ids: list[str]
    refuting_evidence_ids: list[str]
    source_identities: list[str]
    assessments: list[EvidenceAssessment]
    issues: list[VerificationIssue]
    verified_at: datetime

class VerificationGap(BaseModel):
    gap_id: str
    task_id: str
    section_id: str
    claim_id: str | None
    reason_code: str
    description: str
    suggested_query: str
    preferred_source_kinds: list[SourceKind]
    priority: Literal["high", "medium", "low"]
```

不保存伪精确的浮点置信度。判定理由、规则问题和证据 ID 比一个无法校准的分数更可解释。

### 5.5 任务验证摘要

```python
class TaskVerificationSummary(BaseModel):
    task_id: str
    verified_claim_ids: list[str]
    partial_claim_ids: list[str]
    unsupported_claim_ids: list[str]
    conflicted_claim_ids: list[str]
    out_of_range_claim_ids: list[str]
    unresolved_gap_ids: list[str]
    supplement_rounds: int = 0
```

`SectionResult` 增加该摘要和 Writer 可用 Claim ID，不再用阶段 3 的笔记数量暗示事实可靠性。阶段 3 的 TaskCoverage 继续记录研究流程覆盖，两种覆盖含义保持分离。

## 6. Evidence Store

`evidence/` 是纯领域模块，不依赖 Agent、LangGraph、CLI 或具体 Provider。

```text
evidence/
├── __init__.py
├── ids.py          # Source/Evidence/Claim 稳定 ID
├── ingest.py       # RawDocument + ResearchNote → Source/Evidence
└── store.py        # 运行内 upsert、查询和引用反向解析
```

`EvidenceStore` 在单次运行内维护 Source、Evidence 和 Claim 字典。Graph State 保存其可序列化字典；服务对象本身不进入 State。节点增量继续使用字典 reducer。

核心接口：

```python
def ingest_notes(
    documents: Mapping[str, RawDocument],
    notes: Sequence[ResearchNote],
) -> EvidenceIngestResult: ...

class EvidenceStore:
    def upsert_sources(self, values: Iterable[Source]) -> None: ...
    def upsert_evidence(self, values: Iterable[Evidence]) -> None: ...
    def upsert_claims(self, values: Iterable[Claim]) -> None: ...
    def evidence_for_claim(self, claim_id: str) -> list[Evidence]: ...
    def sources_for_claims(self, claim_ids: Sequence[str]) -> list[Source]: ...
```

Evidence Store 不读取搜索摘要，不把 Tavily snippet 当成证据，也不修改原文摘录。

## 7. Claim Extractor

新增 `ClaimExtractorAgent`，只消费当前任务的有效 ResearchNote、已定位 Evidence 和计划时间范围。它不读取整页正文、不调用工具、不判定真假。

模型输出 Claim 草稿与 Evidence ID；本地服务负责：

1. JSON repair 和 Pydantic 校验。
2. 删除未知或 `unlocated` Evidence ID。
3. 拆除没有任何可定位证据的 Claim。
4. 规范化事件时间；明显越界的 Claim 仍保留，但由确定性 Verifier 直接标记为 `out_of_range`，不发送给 LLM。
5. 生成稳定 Claim ID 并按 ID upsert。

结构化抽取失败时，将每个 ResearchNote `key_point` 作为一个 `supporting` Claim 草稿，并关联同一笔记的已定位 Evidence。该降级只保证数据不丢失，仍必须经过 Verifier，不能直接标为验证通过。

## 8. 混合 Verifier

`verification/` 分为确定性规则、LLM 判定和反馈规划：

```text
verification/
├── __init__.py
├── rules.py        # 时间、位置、来源、数字和引用规则
├── service.py      # 规则与 LLM 判定合并
└── feedback.py     # VerificationResult → 有界 VerificationGap
```

### 8.1 确定性规则

每个 Claim 先执行：

- Evidence ID 必须存在，且 `location_status == "exact"`。
- Evidence 的任务、章节和事件时间不得与 Claim 冲突。
- `out_of_range` Evidence 不能支持目标期 Claim。
- 来源独立性按注册域名身份计算。
- `other` 或 `unknown` 来源不能单独支撑关键 Claim。
- Numeric Claim 必须具有 `value_text`；缺少单位、口径或时间基础时记录 blocking issue，除非原文明确表明该字段不适用。
- 关键数字默认需要两个独立合格来源，或一个权威一手来源直接支持完整数值、单位、口径和时间基础。

确定性 blocking issue 不能被 LLM 覆盖。

### 8.2 LLM 语义判定

Verifier 只接收 Claim、Evidence 原文摘录、Source 元数据和规则问题。网页内容被明确标为不可信引用材料，不能改变系统指令。

LLM 对每条 Evidence 返回 `supports / refutes / unrelated` 和简短理由，并指出不同来源是否描述同一口径。一次调用批量处理同一任务的有限 Claim；失败重试一次，单次调用硬超时 60 秒。

### 8.3 最终判定

- `verified`：没有 blocking issue，至少有直接支持证据，并满足来源质量与独立性要求。
- `partially_supported`：存在相关支持，但来源、限定条件或数字字段不足以形成确定事实。
- `unsupported`：没有直接支持证据，或证据与 Claim 无关。
- `conflicted`：存在直接支持和直接反驳，且当前材料不能解释口径差异。
- `out_of_range`：Claim 事件时间明确超出计划范围。

Verifier Provider 调用失败时，确定性规则结果仍保留，但任何 Claim 都不能仅凭本地规则升级为 `verified`；结果降级为 `partially_supported` 或 `unsupported` 并生成 `verifier_error` 缺口。

## 9. 证据驱动补搜

Verifier 只为关键 Claim 的 blocking issue、冲突或无直接支持生成 Gap。低优先级补充 Claim 不自动消耗补搜预算。

Researcher 接收当前任务、VerificationGap、已有查询、现有来源身份和剩余预算。它优先寻找官方公告、论文、产品文档、监管材料或独立合格来源，并避免重复域名。补搜继续使用阶段 3 的 Tavily、排名、每轮最多三个抓取、BGE-M3 召回和压缩链。

单个任务满足任一条件即停止补搜：

- 已完成一次补搜循环。
- 没有 high priority Gap。
- 新增 Evidence 数为零。
- 达到任务、页面、Token、费用、步骤或绝对时间预算。

补搜结束后重新入库新增笔记、增量抽取 Claim，并对当前任务全部 Claim 重新验证一次。第二次验证不得再次路由补搜。

## 10. LangGraph State 与路由

Graph State 新增：

```python
sources: Annotated[dict[str, Source], merge_dicts]
evidence: Annotated[dict[str, Evidence], merge_dicts]
claims: Annotated[dict[str, Claim], merge_dicts]
verification_results: Annotated[dict[str, VerificationResult], merge_dicts]
verification_gaps: Annotated[dict[str, VerificationGap], merge_dicts]
task_verification: Annotated[dict[str, TaskVerificationSummary], merge_dicts]
verification_task_id: str | None
verification_mode: Literal["initial", "supplement", "done"]
used_claim_ids: list[str]
```

`complete_task` 改为生成 provisional SectionResult 并设置 `verification_task_id`，不再立即增加 `current_task_index`。`finalize_task` 在验证完成后写入最终 Claim ID、推进任务索引并清理当前验证上下文。

全局硬预算仍拥有最高优先级，但普通 Researcher 必须为 Claim Extractor、Verifier 和 Writer 留出预算。新增默认配置：

```text
DEEPTRACE_VERIFICATION_TOKEN_RESERVE_RATIO=0.20
DEEPTRACE_RESEARCH_RUNTIME_RATIO=0.70
DEEPTRACE_MAX_VERIFICATION_GAPS_PER_TASK=2
DEEPTRACE_MAX_VERIFICATION_FETCHES_PER_TASK=3
DEEPTRACE_MAX_VERIFICATION_ROUNDS_PER_TASK=1
```

Writer reserve 继续默认为 0.15。普通研究只使用总 Token 的剩余 0.65，并在绝对运行时间的 70% 处停止发起新研究工具调用，让验证和写作使用剩余时间。绝对页面、Token、费用和时间上限不变。

`UsageBreakdown` 增加 `claim_extractor` 与 `verifier`；补搜决策计入 Researcher，补搜压缩计入 Compression。

## 11. Writer 与 Claim 级引用

Writer 不再直接消费 ResearchNote 事实。输入包括 ResearchPlan、SectionResult、可写 Claim、VerificationResult、Evidence 和 Source 元数据，不包含整页正文。

- `verified` 可以写成确定事实。
- `partially_supported` 只能使用“现有证据显示”“材料尚不足”等不确定措辞。
- `unsupported`、`conflicted` 和 `out_of_range` 只能进入缺口或局限说明，不能写入确定事实正文。

Writer 结构化输出报告块，每个事实块携带一个或多个 `claim_ids`。本地渲染器根据 Claim → Evidence → Source 关系添加引用标记和来源列表。任何未知 Claim ID、禁用 verdict 或没有 Claim ID 的事实块都会触发一次纠正重试；第二次仍失败则使用确定性降级报告。

```python
class ReportBlock(BaseModel):
    kind: Literal["fact", "analysis", "limitation"]
    text: str
    claim_ids: list[str]

class VerifiedWriterOutput(BaseModel):
    title: str
    sections: list[VerifiedReportSection]
    used_claim_ids: list[str]
```

确定性渲染器只从 `used_claim_ids` 反向生成来源，因此来源列表不会包含未在报告中使用的抓取页面。`AgentResult` 同时返回 `used_claim_ids`、对应 VerificationResult 和来源 URL。

## 12. 失败与降级

- Evidence 无法定位：保存 `unlocated` 诊断，不进入支持集合。
- Claim Extractor 失败：按 key point 确定性生成待验证 Claim。
- Verifier 失败：不产生 `verified`，保留 Provider 错误并生成 Gap。
- 补搜搜索或抓取失败：记录原始错误码，完成第二次验证并保留缺口。
- 全局预算在验证前耗尽：Writer 只能生成无确定事实的部分报告，说明未完成验证。
- Writer 失败：确定性列出 verified Claim、引用和所有 unresolved Gap。
- 个别任务失败不会删除其他任务已经入库和验证的数据。

所有失败事件必须进入 RunEvent；不得用静态 Claim、Fake Evidence 或人工修改结果补齐真实验收。

## 13. 可观测性

CLI 增加以下事件摘要：

- 入库 Source 数、exact/unlocated Evidence 数。
- 抽取 Claim 数和数字型 Claim 数。
- verified、partial、unsupported、conflicted、out_of_range 数。
- Gap 数、补搜查询数、新增 Evidence 数和补搜停止原因。
- Claim Extractor、Verifier 的 Provider Token。
- 报告实际使用 Claim 数和来源数。

不输出网页全文、API Key、Cookie、敏感请求头或模型隐藏推理。

## 14. 测试与真实验收

自动化测试只覆盖本阶段涉及的确定性逻辑、模型解析、State reducer 和路由，不做规模化评测。

必要测试：

- Source/Evidence/Claim 稳定 ID 和 Pydantic 序列化。
- Evidence 精确字符定位、重复摘录和 unlocated 降级。
- Claim Extractor 删除未知 Evidence ID 和确定性降级。
- 时间、来源独立性、低质量来源和数字完整性规则。
- LLM supports/refutes/unrelated 与 blocking issue 的合并矩阵。
- 每个任务最多补搜一次，第二次验证不会形成循环。
- 全局预算、研究预留、验证预留和 Writer 预留。
- Writer 禁止使用未验证 Claim，并确保 Claim 引用反向解析到实际 Source。
- Verifier、补搜或单页失败不破坏其他任务。
- 阶段 3 非真实套件继续通过。

最终使用真实 LLM API、Tavily、真实网页抓取和本地 `D:\Dev\Models\bge-m3` 运行一个小型端到端问题。验收要求：

- 至少两个 Evidence 能精确回溯到真实 RawDocument 字符位置。
- 至少一个 Claim 得到 `verified`，并在报告中带 Claim 级引用。
- 后发回顾与事件时间保持分离，目标期外事件不成为确定事实。
- 至少检查一个数字 Claim；字段不足时必须降级，不能猜测单位或口径。
- 若产生 high priority Gap，最多执行一次真实补搜并记录新增证据或真实失败原因。
- Writer 来源只来自实际使用 Claim 的 Evidence。
- 无未处理异常，CLI 输出验证统计和各角色 Provider Token。

真实运行得到 `partial` 可以接受，但必须是覆盖、验证缺口或预算导致的诚实状态，不能把未验证内容写成确定事实。

## 15. 阶段边界

阶段 4 新增并真正使用 `evidence/` 与 `verification/`。不创建 `memory/`、`evaluation/` 或 API/Web UI 空目录，不增加数据库依赖，不实现跨运行复用。

阶段 4 完成后，阶段 5 可以持久化 Source、Evidence、Claim 和 VerificationResult，但不能改变本阶段的可追溯语义。阶段 6 再建立固定评测集，衡量 Claim 引用正确率、事实准确率、时间边界和 Verifier 效果。

## 16. 完成定义

1. 单次运行内形成可序列化的 Source → Evidence → Claim → VerificationResult 数据链。
2. 每条支持证据能回溯到真实页面和原文字符位置。
3. 确定性规则和真实 LLM Verifier 共同产生可解释判定。
4. 关键缺口可以触发一次有界 Researcher 补搜，且不存在验证循环。
5. Writer 只把 verified Claim 写成确定事实，并输出 Claim 级引用。
6. 时间越界、来源过弱、数字不完整、冲突和 Provider 失败都有诚实降级。
7. 必要自动化测试和一次真实外部冒烟通过。
8. 阶段 5、6 能力没有提前实现。
