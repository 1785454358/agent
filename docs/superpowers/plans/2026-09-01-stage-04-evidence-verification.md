# Stage 4 Evidence Store and Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在阶段 3 逐任务研究图中加入运行内 Source→Evidence→Claim→VerificationResult 数据链、混合 Verifier、一次有界证据补搜和 Claim 级引用 Writer。

**Architecture:** 保留 Planner、Researcher、现有搜索/抓取/压缩链，在每个任务的 provisional SectionResult 后插入 evidence_ingest、claim_extract、verify 和 finalize_task 节点。Evidence Store 是纯运行内可序列化领域服务；确定性规则先产生 blocking issues，单个真实 LLM Verifier 再判断 Evidence 对 Claim 的支持关系；关键 Gap 最多返回 Researcher 补搜一次，Writer 只消费验证结果。

**Tech Stack:** Python 3.12、Pydantic 2、LangChain、LangGraph、Tavily、HTTPX/Playwright、SentenceTransformers/BGE-M3、pytest、uv。

**Spec:** `docs/superpowers/specs/2026-09-01-stage-04-evidence-verification-design.md`

## Global Constraints

- 代码直接写入正式 `backend/`，保留必要中文注释和现有模块依赖方向。
- Evidence Store 只存在于单次运行和 LangGraph State，不引入数据库、checkpoint 或跨运行复用。
- 搜索摘要不能成为 Evidence；Evidence 摘录必须来自真实 RawDocument，并保存精确字符位置或明确标为 `unlocated`。
- 确定性 blocking issue 不能被 LLM 覆盖；Verifier Provider 失败时不得产生 `verified`。
- 每个任务最多一个补搜循环、两个 high-priority Gap、两个搜索查询和三个新增抓取页面。
- Writer 只把 `verified` Claim 写成确定事实；`partially_supported` 必须降级措辞；其他 verdict 只进入缺口或局限。
- State 只保存可序列化 Pydantic 数据；BGE-M3 numpy 向量继续只存在于 `CompressionRuntime`。
- 不实现 Memory、持久化、FastAPI、Web UI、MCP、新搜索引擎或规模化评测。
- 自动化测试可以使用受控模型桩验证解析和路由，但最终验收不得用 Fake 外部搜索、网页或模型结果。
- 最终必须使用真实 LLM API、Tavily、真实网页抓取和 `D:\Dev\Models\bge-m3` 完成一次端到端冒烟。
- 保留工作区已有无关修改、删除和未跟踪文件，只暂存本计划列出的文件。

---

### Task 1: Evidence、Claim、Verification 模型与 Graph State

**Files:**
- Create: `backend/src/deeptrace/models/evidence.py`
- Create: `backend/src/deeptrace/models/verification.py`
- Modify: `backend/src/deeptrace/models/report.py`
- Modify: `backend/src/deeptrace/models/metrics.py`
- Modify: `backend/src/deeptrace/models/__init__.py`
- Modify: `backend/src/deeptrace/orchestration/state.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/models/test_evidence.py`
- Create: `backend/tests/models/test_verification.py`
- Modify: `backend/tests/orchestration/test_state.py`

**Interfaces:**
- Consumes: `SourceKind`, `TemporalRelation`, `ScraperUsed`, `TaskCoverage`, `TokenUsage`。
- Produces: `Source`, `Evidence`, `NumericDetail`, `Claim`, `EvidenceAssessment`, `VerificationIssue`, `VerificationResult`, `VerificationGap`, `TaskVerificationSummary`；Graph State 字典字段与 reducer；`UsageBreakdown.claim_extractor/verifier`。

- [ ] **Step 1: Write failing model and reducer tests**

```python
def test_evidence_models_are_json_serializable(source, evidence, claim):
    assert Source.model_validate_json(source.model_dump_json()) == source
    assert Evidence.model_validate_json(evidence.model_dump_json()) == evidence
    assert Claim.model_validate_json(claim.model_dump_json()) == claim


def test_verification_summary_defaults():
    value = TaskVerificationSummary(task_id="task-01")
    assert value.verified_claim_ids == []
    assert value.supplement_rounds == 0


def test_role_usage_merges_stage_four_roles():
    left = UsageBreakdown(claim_extractor=TokenUsage(total_tokens=3))
    right = UsageBreakdown(verifier=TokenUsage(total_tokens=5))
    merged = merge_usage_breakdown(left, right)
    assert merged.total.total_tokens == 8
```

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/models/test_evidence.py tests/models/test_verification.py tests/orchestration/test_state.py -v`

Expected: FAIL because stage 4 models and fields do not exist.

- [ ] **Step 3: Implement the exact models**

Use the spec field names verbatim. Important validation:

```python
class Evidence(BaseModel):
    evidence_id: str
    source_id: str
    doc_id: str
    note_id: str
    task_id: str
    section_id: str
    quote: str = Field(min_length=1)
    quote_hash: str
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    location_status: EvidenceLocationStatus
    event_start_date: date | None = None
    event_end_date: date | None = None
    temporal_relation: TemporalRelation = "not_applicable"

    @model_validator(mode="after")
    def validate_location(self):
        if self.location_status == "exact" and (
            self.char_start is None or self.char_end is None
        ):
            raise ValueError("exact Evidence 必须包含字符位置")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end <= self.char_start:
                raise ValueError("Evidence 字符结束位置必须晚于开始位置")
        return self
```

`SectionResult` adds `claim_ids: list[str]` and `verification: TaskVerificationSummary | None`. `UsageBreakdown` adds `claim_extractor` and `verifier`; its `total` includes all six roles.

- [ ] **Step 4: Add serializable State fields and reducers**

Add the `sources`, `evidence`, `claims`, `verification_results`, `verification_gaps`, `task_verification`, `verification_task_id`, `verification_mode`, `verification_tool_rounds` and `used_claim_ids` fields defined by the spec. Update `merge_usage_breakdown` for both new roles and add reusable fixtures without changing existing fixture defaults.

- [ ] **Step 5: Run tests to verify GREEN**

Run: `uv run pytest tests/models/test_evidence.py tests/models/test_verification.py tests/models/test_quality.py tests/orchestration/test_state.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/deeptrace/models/evidence.py backend/src/deeptrace/models/verification.py backend/src/deeptrace/models/report.py backend/src/deeptrace/models/metrics.py backend/src/deeptrace/models/__init__.py backend/src/deeptrace/orchestration/state.py backend/tests/conftest.py backend/tests/models/test_evidence.py backend/tests/models/test_verification.py backend/tests/orchestration/test_state.py
git commit -m "feat: add stage 4 evidence models"
```

### Task 2: Stable IDs、Evidence Ingest 与运行内 Store

**Files:**
- Create: `backend/src/deeptrace/evidence/__init__.py`
- Create: `backend/src/deeptrace/evidence/ids.py`
- Create: `backend/src/deeptrace/evidence/ingest.py`
- Create: `backend/src/deeptrace/evidence/store.py`
- Create: `backend/tests/evidence/test_ids.py`
- Create: `backend/tests/evidence/test_ingest.py`
- Create: `backend/tests/evidence/test_store.py`
- Modify: `backend/tests/test_module_layout.py`

**Interfaces:**
- Consumes: `RawDocument`, valid `ResearchNote`, stage 4 models。
- Produces: `source_id(doc_id: str) -> str`, `evidence_id(source_id: str, note_id: str, quote_hash: str, char_start: int | None) -> str`, `claim_id(task_id: str, section_id: str, text: str) -> str`, `EvidenceIngestResult`, `ingest_notes(documents: Mapping[str, RawDocument], notes: Sequence[ResearchNote], existing_sources: Mapping[str, Source] | None = None) -> EvidenceIngestResult`, `EvidenceStore` query/upsert API。

- [ ] **Step 1: Write failing ID, location, conflict and reverse-lookup tests**

```python
def test_ingest_locates_exact_quote(raw_document, research_note):
    note = research_note.model_copy(
        update={"evidence_snippets": ["整页正文唯一标记"]}
    )
    result = ingest_notes({raw_document.doc_id: raw_document}, [note])
    item = next(iter(result.evidence.values()))
    assert item.location_status == "exact"
    assert raw_document.content[item.char_start:item.char_end] == item.quote


def test_unmatched_quote_is_diagnostic_only(raw_document, research_note):
    note = research_note.model_copy(update={"evidence_snippets": ["并不存在"]})
    result = ingest_notes({raw_document.doc_id: raw_document}, [note])
    assert next(iter(result.evidence.values())).location_status == "unlocated"
```

Add conflict tests proving two different source kinds for one document downgrade to `unknown`, and Store tests proving Claim→Evidence→Source reverse lookup preserves first-use order.

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/evidence tests/test_module_layout.py -v`

Expected: FAIL because the evidence package is absent.

- [ ] **Step 3: Implement deterministic IDs and ingestion**

```python
def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part).strip() for part in parts)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def locate_quote(content: str, quote: str) -> tuple[int | None, int | None]:
    start = content.find(quote)
    return (None, None) if start < 0 else (start, start + len(quote))
```

`ingest_notes` only accepts non-irrelevant notes whose temporal relation is `in_range`, `retrospective`, or `not_applicable`. It creates one Source per document, one Evidence per non-empty snippet, uses the first exact occurrence, and emits a warning for missing document, source-kind conflict, or unlocated quote. It never ingests Tavily snippets.

- [ ] **Step 4: Implement the runtime store**

`EvidenceStore` copies input dictionaries, performs immutable-style upserts, returns evidence in Claim evidence ID order, and resolves unique Sources in first-use order.

- [ ] **Step 5: Run tests to verify GREEN**

Run: `uv run pytest tests/evidence tests/test_module_layout.py -v`

Expected: PASS and no `memory/` or `evaluation/` package exists.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/deeptrace/evidence backend/tests/evidence backend/tests/test_module_layout.py
git commit -m "feat: build runtime evidence store"
```

### Task 3: Claim Extractor 与确定性降级

**Files:**
- Create: `backend/src/deeptrace/prompts/claim_extractor.py`
- Modify: `backend/src/deeptrace/prompts/__init__.py`
- Create: `backend/src/deeptrace/agent/claim_extractor.py`
- Modify: `backend/src/deeptrace/agent/__init__.py`
- Create: `backend/tests/agent/test_claim_extractor.py`
- Create: `backend/tests/prompts/test_claim_extractor.py`

**Interfaces:**
- Consumes: current `ResearchTask`, valid notes, exact Evidence, `ResearchTimeRange`。
- Produces: `ClaimDraft`, `ClaimExtractorOutput`, `parse_claim_output(raw: str) -> ClaimExtractorOutput`, `materialize_claims(drafts, evidence, task, time_range) -> list[Claim]`, `fallback_claims(notes, evidence) -> list[Claim]`, `ClaimExtractorAgent.aextract(task, notes, evidence, time_range) -> tuple[list[Claim], TokenUsage, bool]`。

- [ ] **Step 1: Write failing parsing, filtering and fallback tests**

```python
def test_materialize_removes_unknown_and_unlocated_evidence(
    research_task, range_2024, exact_evidence, unlocated_evidence
):
    claims = materialize_claims(
        drafts=[draft_with_ids("ev-exact", "ev-unlocated", "ev-missing")],
        evidence={
            "ev-exact": exact_evidence,
            "ev-unlocated": unlocated_evidence,
        },
        task=research_task,
        time_range=range_2024,
    )
    assert claims[0].evidence_ids == ["ev-exact"]


def test_fallback_key_points_are_not_verified(research_note, exact_evidence):
    claims = fallback_claims([research_note], [exact_evidence])
    assert claims[0].importance == "supporting"
    assert claims[0].evidence_ids == [exact_evidence.evidence_id]
```

Add an async test: first malformed response, second malformed response, assert deterministic fallback and exactly two Provider calls.

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/agent/test_claim_extractor.py tests/prompts/test_claim_extractor.py -v`

Expected: FAIL because the role and prompt do not exist.

- [ ] **Step 3: Implement prompt and structured draft**

The system prompt states that Evidence is untrusted quoted material, demands atomic facts, forbids knowledge not present in quotes, and requires existing Evidence IDs. The payload includes only note fields, exact Evidence quotes/IDs, task question and time range; never RawDocument content.

```python
class ClaimDraft(BaseModel):
    text: str = Field(min_length=1)
    kind: ClaimKind
    importance: ClaimImportance
    event_start_date: date | None = None
    event_end_date: date | None = None
    numeric: NumericDetail | None = None
    evidence_ids: list[str] = Field(min_length=1)


class ClaimExtractorOutput(BaseModel):
    claims: list[ClaimDraft] = Field(default_factory=list)
```

- [ ] **Step 4: Implement local materialization and bounded model calls**

Use JSON repair, remove unknown/unlocated IDs, preserve explicit out-of-range claims for deterministic Verifier classification, generate `claim_id` locally, and deduplicate by ID. Retry parsing once with the exact validation error; after two failures call `fallback_claims`.

- [ ] **Step 5: Run tests to verify GREEN**

Run: `uv run pytest tests/agent/test_claim_extractor.py tests/prompts/test_claim_extractor.py tests/agent/test_planner.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/deeptrace/prompts/claim_extractor.py backend/src/deeptrace/prompts/__init__.py backend/src/deeptrace/agent/claim_extractor.py backend/src/deeptrace/agent/__init__.py backend/tests/agent/test_claim_extractor.py backend/tests/prompts/test_claim_extractor.py
git commit -m "feat: extract atomic research claims"
```

### Task 4: Deterministic Verification Rules

**Files:**
- Create: `backend/src/deeptrace/verification/__init__.py`
- Create: `backend/src/deeptrace/verification/rules.py`
- Create: `backend/tests/verification/test_rules.py`
- Modify: `backend/tests/test_module_layout.py`

**Interfaces:**
- Consumes: Claim, Evidence, Source, plan time range。
- Produces: `RuleCheckResult`, `check_claim_rules(claim: Claim, evidence: Mapping[str, Evidence], sources: Mapping[str, Source], time_range: ResearchTimeRange | None) -> RuleCheckResult`, `eligible_evidence(claim, evidence) -> list[Evidence]`, `source_identities(evidence, sources) -> list[str]`。

- [ ] **Step 1: Write the verification matrix tests**

Cover exact location, missing Evidence, out-of-range event, one weak source, two same-domain sources, two independent qualified sources, authoritative direct source, and numeric completeness.

```python
def test_numeric_claim_requires_unit_scope_and_time_basis(
    numeric_claim, evidence_by_id, sources_by_id, range_2024
):
    result = check_claim_rules(
        numeric_claim, evidence_by_id, sources_by_id, range_2024
    )
    assert {item.code for item in result.blocking_issues} == {
        "numeric_unit_missing",
        "numeric_scope_missing",
        "numeric_time_basis_missing",
    }


def test_two_subdomains_are_one_source_identity(
    key_claim, evidence_from_two_subdomains, subdomain_sources
):
    result = check_claim_rules(
        key_claim, evidence_from_two_subdomains, subdomain_sources, None
    )
    assert result.source_identities == ["example.com"]
```

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/verification/test_rules.py tests/test_module_layout.py -v`

Expected: FAIL because verification rules do not exist.

- [ ] **Step 3: Implement pure deterministic rules**

`RuleCheckResult` contains eligible Evidence IDs, source identities, issues and an optional forced verdict. Use existing `source_identity`. Rules never call a model and never upgrade a Claim to verified.

```python
class RuleCheckResult(BaseModel):
    eligible_evidence_ids: list[str] = Field(default_factory=list)
    source_identities: list[str] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    forced_verdict: VerificationVerdict | None = None

    @property
    def blocking_issues(self) -> list[VerificationIssue]:
        return [item for item in self.issues if item.severity == "blocking"]
```

```python
if claim.event_start_date and claim.event_end_date and time_range:
    relation = normalize_temporal_relation(
        time_range, None, claim.event_start_date, claim.event_end_date
    )
    if relation == "out_of_range":
        return RuleCheckResult(
            forced_verdict="out_of_range",
            issues=[VerificationIssue(
                code="claim_out_of_range",
                severity="blocking",
                message="Claim 事件时间超出研究范围",
            )],
        )
```

For key claims, one official/academic direct source is eligible for semantic verification; reputable secondary material requires two independent qualified identities. Numeric key claims require two independent qualified identities unless one official/academic source has complete numeric fields.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/verification/test_rules.py tests/orchestration/test_note_quality.py tests/context/test_temporal.py tests/test_module_layout.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/deeptrace/verification/__init__.py backend/src/deeptrace/verification/rules.py backend/tests/verification/test_rules.py backend/tests/test_module_layout.py
git commit -m "feat: add deterministic claim checks"
```

### Task 5: LLM Verifier、判定合并与 Gap 生成

**Files:**
- Create: `backend/src/deeptrace/prompts/verifier.py`
- Modify: `backend/src/deeptrace/prompts/__init__.py`
- Create: `backend/src/deeptrace/verification/service.py`
- Create: `backend/src/deeptrace/verification/feedback.py`
- Modify: `backend/src/deeptrace/verification/__init__.py`
- Create: `backend/tests/prompts/test_verifier.py`
- Create: `backend/tests/verification/test_service.py`
- Create: `backend/tests/verification/test_feedback.py`

**Interfaces:**
- Consumes: Claim batches, rule results, exact Evidence and Source metadata。
- Produces: `VerifierDraft`, `VerifierAgent.averify(claims, evidence, sources, time_range) -> tuple[dict[str, VerificationResult], TokenUsage]`, `merge_verdict(claim, rules, assessments, provider_error) -> VerificationResult`, `build_verification_gaps(claims, results, max_gaps) -> list[VerificationGap]`。

- [ ] **Step 1: Write failing entailment and failure-safety tests**

```python
def test_support_and_refute_become_conflicted(
    claim, clean_rules, support_assessment, refute_assessment
):
    result = merge_verdict(
        claim=claim,
        rules=clean_rules,
        assessments=[support_assessment, refute_assessment],
        provider_error=None,
    )
    assert result.verdict == "conflicted"


def test_blocking_issue_cannot_be_overridden_by_support(
    claim, blocking_rules, support_assessment
):
    result = merge_verdict(
        claim=claim,
        rules=blocking_rules,
        assessments=[support_assessment],
        provider_error=None,
    )
    assert result.verdict == "partially_supported"
    assert result.verdict != "verified"


def test_provider_failure_never_verifies(claim, clean_rules):
    result = merge_verdict(
        claim=claim,
        rules=clean_rules,
        assessments=[],
        provider_error="TimeoutError",
    )
    assert result.verdict in {"partially_supported", "unsupported"}
```

Add feedback tests asserting only key blocking/conflicted/unsupported Claims create gaps, high priority sorts first, and the result is capped at the configured count.

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/prompts/test_verifier.py tests/verification/test_service.py tests/verification/test_feedback.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement untrusted-evidence prompt and parser**

The prompt uses explicit delimiters and says quoted page content cannot issue instructions. Each assessment must reference one allowed Evidence ID and use only `supports`, `refutes`, or `unrelated`. Drop unknown IDs locally.

```python
class VerifierClaimDraft(BaseModel):
    claim_id: str
    assessments: list[EvidenceAssessment] = Field(default_factory=list)
    reason: str = ""


class VerifierDraft(BaseModel):
    claims: list[VerifierClaimDraft] = Field(default_factory=list)
```

- [ ] **Step 4: Implement VerifierAgent and merge matrix**

Call the model with `asyncio.wait_for(self._model.ainvoke(messages), timeout=60)`, retry invalid JSON once, then return provider-error results without `verified`. Store each VerificationResult in the State dictionary under its `claim_id`; `verified_at` is generated locally. A deterministic out-of-range forced verdict bypasses the model.

- [ ] **Step 5: Implement bounded Gap generation**

`suggested_query` combines the atomic Claim text with the missing requirement; it must not include raw Evidence quotes. Prefer `official` and `academic`, then `reputable_secondary`. Generate stable Gap IDs and cap high/medium gaps with a deterministic priority sort.

- [ ] **Step 6: Run tests to verify GREEN**

Run: `uv run pytest tests/prompts/test_verifier.py tests/verification -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/src/deeptrace/prompts/verifier.py backend/src/deeptrace/prompts/__init__.py backend/src/deeptrace/verification backend/tests/prompts/test_verifier.py backend/tests/verification
git commit -m "feat: verify claims and plan evidence gaps"
```

### Task 6: Verification Budget 与 Researcher 补搜模式

**Files:**
- Modify: `backend/.env.example`
- Modify: `backend/src/deeptrace/config/settings.py`
- Modify: `backend/src/deeptrace/orchestration/budget.py`
- Modify: `backend/src/deeptrace/prompts/researcher.py`
- Modify: `backend/src/deeptrace/agent/researcher.py`
- Modify: `backend/src/deeptrace/orchestration/tool_executor.py`
- Modify: `backend/tests/config/test_settings.py`
- Modify: `backend/tests/orchestration/test_budget.py`
- Modify: `backend/tests/agent/test_researcher.py`
- Modify: `backend/tests/orchestration/test_tool_executor.py`

**Interfaces:**
- Consumes: VerificationGap list and stage 3 tool chain。
- Produces: new settings, `verification_token_reserve`, `regular_research_deadline_reached`, optional `verification_gaps` Researcher prompt input, bounded supplemental fetch behavior。

- [ ] **Step 1: Write failing settings and budget tests**

```python
def test_stage_four_budget_defaults(settings):
    assert settings.verification_token_reserve_ratio == 0.20
    assert settings.research_runtime_ratio == 0.70
    assert settings.max_verification_gaps_per_task == 2
    assert settings.max_verification_fetches_per_task == 3
    assert settings.max_verification_rounds_per_task == 1


def test_task_allowance_reserves_verifier_and_writer(
    research_plan, running_state, settings
):
    remaining_tasks = len(research_plan.tasks)
    expected_pool = (
        settings.max_api_tokens
        - writer_token_reserve(settings)
        - verification_token_reserve(settings)
    )
    assert task_token_allowance(running_state, settings) == (
        expected_pool // remaining_tasks
    )
```

Add a Researcher prompt test asserting gap descriptions, preferred source kinds and existing domains are present but raw page content is absent. Add executor test asserting supplement mode still maps every tool call ID and accepts no more than `max_verification_fetches_per_task` fetches.

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/config/test_settings.py tests/orchestration/test_budget.py tests/agent/test_researcher.py tests/orchestration/test_tool_executor.py -v`

Expected: FAIL.

- [ ] **Step 3: Add validated settings**

```text
DEEPTRACE_VERIFICATION_TOKEN_RESERVE_RATIO=0.20
DEEPTRACE_RESEARCH_RUNTIME_RATIO=0.70
DEEPTRACE_MAX_VERIFICATION_GAPS_PER_TASK=2
DEEPTRACE_MAX_VERIFICATION_FETCHES_PER_TASK=3
DEEPTRACE_MAX_VERIFICATION_ROUNDS_PER_TASK=1
```

Validate ratios in `[0.05, 0.40]`; require writer + verification reserve `< 0.80`. Validate counts in `[1, 10]`.

- [ ] **Step 4: Update budget functions**

```python
def verification_token_reserve(settings: Settings) -> int:
    return int(settings.max_api_tokens * settings.verification_token_reserve_ratio)


def regular_research_deadline_reached(state, settings, now) -> bool:
    return elapsed_seconds(state["started_at"], now) >= (
        settings.max_runtime_seconds * settings.research_runtime_ratio
    )
```

Subtract writer and verification reserves in `task_token_allowance`. Only regular research obeys the 70% deadline; Evidence, Claim, Verifier and Writer still obey the absolute budget.

- [ ] **Step 5: Add bounded gap context to Researcher**

Extend `ResearcherAgent.adecide` and `build_researcher_messages` with optional `verification_gaps`, `existing_source_identities` and `research_mode`. In supplement mode, require gap-focused search/fetch or explicit completion, forbid unrelated broadening, and retain the existing tool schemas.

- [ ] **Step 6: Run tests to verify GREEN**

Run: `uv run pytest tests/config/test_settings.py tests/orchestration/test_budget.py tests/agent/test_researcher.py tests/orchestration/test_tool_executor.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/.env.example backend/src/deeptrace/config/settings.py backend/src/deeptrace/orchestration/budget.py backend/src/deeptrace/prompts/researcher.py backend/src/deeptrace/agent/researcher.py backend/src/deeptrace/orchestration/tool_executor.py backend/tests/config/test_settings.py backend/tests/orchestration/test_budget.py backend/tests/agent/test_researcher.py backend/tests/orchestration/test_tool_executor.py
git commit -m "feat: reserve bounded verification research"
```

### Task 7: LangGraph 逐任务验证闭环

**Files:**
- Modify: `backend/src/deeptrace/orchestration/nodes.py`
- Modify: `backend/src/deeptrace/orchestration/graph.py`
- Modify: `backend/src/deeptrace/orchestration/__init__.py`
- Modify: `backend/src/deeptrace/agent/service.py`
- Modify: `backend/tests/orchestration/test_nodes.py`
- Modify: `backend/tests/orchestration/test_graph.py`
- Modify: `backend/tests/agent/test_service.py`

**Interfaces:**
- Consumes: Evidence ingest, ClaimExtractorAgent, VerifierAgent, Gap feedback and existing ResearchToolExecutor。
- Produces: evidence/claim/verify/start_verification_research/verification_research/finalize_task nodes, conditional routes and fully initialized stage 4 State。

- [ ] **Step 1: Write failing routing and no-loop tests**

```python
def test_completed_task_routes_to_evidence_before_next_task():
    assert route_after_task_completion(state) == "evidence_ingest"


def test_initial_verification_with_high_gap_routes_to_supplement():
    assert route_after_verification(initial_gap_state) == "start_verification_research"


def test_second_verification_always_finalizes():
    assert route_after_verification(supplement_gap_state) == "finalize_task"


def test_tools_return_to_verification_research_in_supplement_mode():
    assert route_after_tools(supplement_state) == "verification_research"
```

Add a node test proving `complete_task_node` does not advance the index and `finalize_task_node` advances exactly once.

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/orchestration/test_graph.py tests/orchestration/test_nodes.py tests/agent/test_service.py -v`

Expected: FAIL.

- [ ] **Step 3: Split task completion from finalization**

`complete_task_node` keeps the provisional section, sets `verification_task_id`, `verification_mode="initial"`, and leaves `current_task_index` unchanged. `finalize_task_node` writes Claim IDs and TaskVerificationSummary into SectionResult, increments once, clears messages/gaps/current verification fields, then routes to the next task or Writer.

- [ ] **Step 4: Implement Evidence, Claim and Verify nodes**

Each node only coordinates one domain service. It updates dictionaries via reducers, emits structured RunEvent counts, and accounts Claim Extractor/Verifier usage through `_usage_update`. `verify_node` replaces only current-task results/gaps by deterministic ID; stale gaps from the first pass are removed with an explicit current-task dictionary rebuild before returning State.

- [ ] **Step 5: Implement one supplemental tool loop**

`start_verification_research_node` increments `supplement_rounds`, sets mode `supplement`, resets `verification_tool_rounds` and `recent_new_note_count`. `verification_research_node` calls the existing Researcher with the top two high-priority gaps. It routes tool calls through the existing tools node; after new notes arrive or two tool decision rounds complete, it returns to Evidence ingest. It never routes to `complete_task` and never starts a second supplement cycle.

- [ ] **Step 6: Wire the graph**

```text
complete_task → evidence_ingest → claim_extract → verify
verify → start_verification_research | finalize_task
start_verification_research → verification_research
verification_research → tools | evidence_ingest
tools → research | verification_research
finalize_task → start_task | writer
```

Initialize all stage 4 fields in `ResearchAgent.arun`; inject ClaimExtractorAgent and VerifierAgent in `build_real_agent`; increase recursion limit only by the exact bounded verification node allowance.

- [ ] **Step 7: Run tests to verify GREEN**

Run: `uv run pytest tests/orchestration/test_graph.py tests/orchestration/test_nodes.py tests/orchestration/test_state.py tests/agent/test_service.py -v`

Expected: PASS and the no-loop test proves each task has at most one supplement cycle.

- [ ] **Step 8: Commit**

```powershell
git add backend/src/deeptrace/orchestration/nodes.py backend/src/deeptrace/orchestration/graph.py backend/src/deeptrace/orchestration/__init__.py backend/src/deeptrace/agent/service.py backend/tests/orchestration/test_nodes.py backend/tests/orchestration/test_graph.py backend/tests/agent/test_service.py
git commit -m "feat: close the claim verification loop"
```

### Task 8: Verified Writer、Claim 引用与 CLI 结果

**Files:**
- Modify: `backend/src/deeptrace/prompts/writer.py`
- Modify: `backend/src/deeptrace/agent/writer.py`
- Modify: `backend/src/deeptrace/agent/service.py`
- Modify: `backend/src/deeptrace/observability/token_metrics.py`
- Modify: `backend/src/deeptrace/cli.py`
- Modify: `backend/tests/agent/test_writer.py`
- Modify: `backend/tests/agent/test_service.py`
- Modify: `backend/tests/observability/test_token_metrics.py`
- Modify: `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: Sections, Claims, VerificationResults, Evidence, Sources and unresolved Gaps。
- Produces: `ReportBlock`, `VerifiedReportSection`, `VerifiedWriterOutput`, local citation validator/renderer, `AgentResult.used_claim_ids/verification_results`, authoritative source list and CLI stage 4 statistics。

- [ ] **Step 1: Write failing Writer and source lineage tests**

```python
def test_writer_rejects_unsupported_claim_id(
    output_using_unsupported, verification_results
):
    violations = validate_writer_output(
        output_using_unsupported, verification_results
    )
    assert "claim_not_writable" in violations


def test_renderer_resolves_claim_to_exact_source(
    verified_writer_output,
    claims_by_id,
    verification_results,
    evidence_by_id,
    sources_by_id,
    source,
):
    markdown = render_verified_output(
        verified_writer_output,
        claims_by_id,
        verification_results,
        evidence_by_id,
        sources_by_id,
    )
    assert "[[claim:" not in markdown
    assert source.final_url in markdown


def test_sources_only_include_used_claims(
    used_claim, claims_by_id, evidence_by_id, sources_by_id, used_source
):
    assert sources_from_used_claims(
        [used_claim.claim_id], claims_by_id, evidence_by_id, sources_by_id
    ) == [used_source.final_url]
```

Add an async retry test where the first Writer response uses an unsupported Claim and the second uses a verified Claim. Add a deterministic fallback test with no verified Claims.

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/agent/test_writer.py tests/agent/test_service.py tests/observability/test_token_metrics.py tests/test_cli.py -v`

Expected: FAIL.

- [ ] **Step 3: Replace note-fact Writer input with verified Claim input**

`build_writer_messages` serializes allowed Claims, verdicts, Evidence IDs and Source metadata, but not RawDocument content. `ReportBlock(kind="fact")` accepts only verified Claim IDs; `analysis` may use verified and partial IDs but partial text must include configured uncertainty markers; `limitation` can reference any result or no Claim.

```python
class ReportBlock(BaseModel):
    kind: Literal["fact", "analysis", "limitation"]
    text: str = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)


class VerifiedReportSection(BaseModel):
    heading: str = Field(min_length=1)
    blocks: list[ReportBlock] = Field(default_factory=list)


class VerifiedWriterOutput(BaseModel):
    title: str = Field(min_length=1)
    sections: list[VerifiedReportSection] = Field(default_factory=list)
    used_claim_ids: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Implement deterministic citation rendering**

Render each fact/analysis block with stable footnotes derived from its Claim IDs. A footnote lists the exact Evidence quote and Source URL; the final source list is deduplicated from `used_claim_ids` in first-use order. Validate unknown IDs, forbidden verdicts and fact blocks without Claim IDs; retry once then fallback.

- [ ] **Step 5: Update AgentResult, status and CLI**

Return `used_claim_ids`, only their VerificationResults, and sources resolved through Evidence Store. Completed status requires every completed task to have at least one verified key Claim and no unresolved high-priority Gap; otherwise a generated report is partial. CLI prints Evidence location counts, verdict counts, Gap/supplement counts, actual used Claims/sources, and Claim Extractor/Verifier Provider Token.

- [ ] **Step 6: Run tests to verify GREEN**

Run: `uv run pytest tests/agent/test_writer.py tests/agent/test_service.py tests/observability/test_token_metrics.py tests/test_cli.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/src/deeptrace/prompts/writer.py backend/src/deeptrace/agent/writer.py backend/src/deeptrace/agent/service.py backend/src/deeptrace/observability/token_metrics.py backend/src/deeptrace/cli.py backend/tests/agent/test_writer.py backend/tests/agent/test_service.py backend/tests/observability/test_token_metrics.py backend/tests/test_cli.py
git commit -m "feat: write reports from verified claims"
```

### Task 9: Integration、Documentation 与真实验收

**Files:**
- Modify: `backend/README.md`
- Modify: `docs/README.md`
- Modify: `docs/roadmap/deeptrace-evolution.md`
- Modify: `docs/architecture/deeptrace-target-architecture.md`
- Modify: `docs/superpowers/specs/2026-09-01-stage-04-evidence-verification-design.md`
- Test: `backend/tests/`

**Interfaces:**
- Consumes: Tasks 1–8 and real `.env` credentials。
- Produces: integrated stage 4 CLI, documented Evidence/Verifier contracts and one real acceptance record。

- [ ] **Step 1: Run focused stage 4 integration tests**

```powershell
uv run pytest tests/models/test_evidence.py tests/models/test_verification.py tests/evidence tests/agent/test_claim_extractor.py tests/verification tests/orchestration/test_budget.py tests/orchestration/test_graph.py tests/orchestration/test_nodes.py tests/agent/test_writer.py tests/agent/test_service.py tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 2: Run existing non-real suite and compile check**

```powershell
uv lock --check
uv run pytest -m "not real"
uv run python -m compileall src tests
```

Expected: all tests PASS and both commands exit 0.

- [ ] **Step 3: Run one real end-to-end smoke**

```powershell
$env:DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY='true'
$env:PYTHONUNBUFFERED='1'
uv run deeptrace "2024年AI Agent领域有哪些重要进展？"
```

Acceptance evidence:

- at least two exact Evidence records point into real RawDocument content;
- at least one Claim is verified and appears with a Claim-level citation;
- later retrospective sources remain allowed but later events are not definite 2024 facts;
- at least one numeric Claim is checked and incomplete fields cause downgrade;
- any high-priority Gap triggers no more than one real supplement cycle, or the run records why no supplement was needed/allowed;
- final sources are derived only from used Claims;
- CLI shows Evidence, verdict, Gap, supplement and six-role Provider usage counts;
- partial status is honest and there is no unhandled exception or Fake external result.

If one real provider or page fails, preserve its actual error and retry only the affected smoke once. Do not replace external results with fixtures or static content.

- [ ] **Step 4: Update documentation from actual behavior**

Document models, exact quote positions, verifier verdicts, one-cycle supplement limits, budget ratios, CLI output and run commands in `backend/README.md`. Mark stage 4 complete only after the real smoke reaches Writer with Claim lineage. Update docs README and roadmap next step to stage 5; update target architecture statements from planned to implemented without adding stage 5 code.

- [ ] **Step 5: Check secrets and preserve scope**

```powershell
git diff --check
git status --short
git diff --name-only
git grep -n -I -E "sk-[A-Za-z0-9_-]{12,}|TAVILY_API_KEY=.*[^=[:space:]]" -- backend ":(exclude)backend/.env"
```

Expected: no secret values; pre-existing unrelated deletions, modifications and untracked files remain unchanged.

- [ ] **Step 6: Commit documentation**

```powershell
git add backend/README.md docs/README.md docs/roadmap/deeptrace-evolution.md docs/architecture/deeptrace-target-architecture.md docs/superpowers/specs/2026-09-01-stage-04-evidence-verification-design.md
git commit -m "docs: complete stage 4 evidence verification"
```

## Final Acceptance

- [ ] Source, Evidence, Claim and VerificationResult are serializable and linked by stable IDs.
- [ ] Evidence quotes are exact RawDocument substrings or explicitly unlocated.
- [ ] Search summaries never become Evidence.
- [ ] Deterministic blocking issues cannot be overridden by the LLM.
- [ ] Provider failure never produces verified Claims.
- [ ] Important numbers retain value, unit, scope and time basis or are downgraded.
- [ ] Each task performs at most one bounded evidence supplement cycle.
- [ ] Writer definite facts use only verified Claims and render Claim-level citations.
- [ ] Source lists contain only Sources behind actually used Claims.
- [ ] State, budgets, events and role usage remain serializable and explainable.
- [ ] Existing stage 3 search, scraping, compression and failure behavior does not regress.
- [ ] Automated tests and one real LLM/Tavily/Web/BGE-M3 smoke pass without Fake acceptance data.
- [ ] No stage 5 or 6 package, database, API, Web UI or evaluation harness is added.
