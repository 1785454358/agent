# Structured Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复结构损坏和目标实体被通用词挤掉的取材缺陷，保持真实联网评分口径与预算。

**Architecture:** 在已有抓取器、共享原文选段器与阅读适配器内局部替换，不加服务。正文先结构保真，选段按实际查询实体和固定需求平衡，预览完整组适配；引用/授权/恢复仍沿用现有 Harness。

**Tech Stack:** Python 3.12、BeautifulSoup、已有 Trafilatura 2.2.0、pytest、现有 Ragas 0.4.3 独立环境。

**Spec:** `docs/superpowers/specs/2026-10-04-structured-retrieval-design.md`

**Progress:** Task 1–3 已按 TDD 实施并完成全量回归（1187 passed）；评分环境34 passed。Task 4 已完成一次性三模式研究、评分、快照核对及审计。主模式F1=0.86，但仍partial且来源/效率验收失败，未扩大付费实验。评估侧重复旧排序已用实际轨迹精确重放，需下一步独立替换。详见 `docs/evaluation/structured-retrieval-validation-20261004.md`。

## Global Constraints

- 不新增 Agent、向量服务、模型调用、依赖或评分规则。
- 默认原文读预算 2,000 字符、可申请上限 3,000 字符、工具预览 4,000 字符不变。
- 20,000 字符存储上限、响应字节上限和 URL/重定向/DNS 安全检查不变。
- 每分支 12 轮；每运行 40 logical / 80 Provider / 24 Gateway / 360 秒；研究批次 120 logical / 240 Provider；评分批次 48 Provider。
- 保持 doubao-seed-2.0-lite、temperature=0、输出 4096、Answer 2,000 字符、记忆关闭。
- 抓取与阅读合并、版本来源约束执行、Goal 判分审计不在本轮范围。
- 不覆盖或重评分旧结果，不择优重跑。主模式 F1 至少 0.80 且 completed、来源/关键行为合格后才扩大实验。
- 当前没有 subagent-driven-development/executing-plans 技能；由本会话按 TDD 逐项执行，不声称使用缺失技能或独立评审。保留脏工作区，源码不整文件提交已有改动。

## Task 1: 结构保真的抓取提取

**Files:** Modify `backend/src/deeptrace/tools/scraper/fetcher.py`; create `backend/tests/tools/scraper/test_structured_extraction.py`.

**Interfaces:** Consumes HTML 与 ExtractionCandidate；produces existing `AsyncWebFetcher.fetch(url) -> RawDocument`、`_extract_bs4(html) -> str`，不改变入库/安全接口。`select_best_extraction` 可接受最低门槛谓词以选择第一个可用候选。

- [x] 保存 src/tests 起始副本到全新 `tmp/structured-retrieval-start-20261004`，不复制 .env。
- [x] 新增真实提取回归，明确捕获行内代码拆行、丢失段落、嵌套块重复和错误最长策略。

```python
def test_inline_api_stays_in_its_conditional_paragraph():
    html = '<main><p>If <code>return_exceptions</code> is false, tasks continue.</p><p>Do not swallow cancellation.</p></main>'
    body = AsyncWebFetcher._extract_bs4(html)
    assert 'If return_exceptions is false, tasks continue.' in body
    assert '\n\n' in body
```

- [x] 在 backend 执行 `.venv/Scripts/python.exe -m pytest tests/tools/scraper/test_structured_extraction.py -q`，确认断言失败而非导入/环境错误。
- [x] 主提取改 Markdown；依现有 `_is_usable` 按候选顺序优先主提取，失败才选 BS4/浏览器；在 BS4 用块边界分隔并保留行内节点、代码换行。

```python
usable = next((c for c in candidates if is_usable(c.text)), None)
best = usable or max(candidates, key=lambda c: len(c.text.strip()))
```

- [x] 执行上述新测试及 `tests/tools/scraper tests/tools/test_source_identity.py`；在变更副本差异中复核门槛、SSRF 与来源身份未放宽。保留脏工作区，本轮生产与依赖此前改动的测试文件不整文件提交；文档单独留档。

## Task 2: 原文目标实体与完整段落选段

**Files:** Modify `backend/src/deeptrace/tools/evidence_views.py`; create `backend/tests/tools/test_structured_retrieval.py`; update only superseded assertions in `backend/tests/tools/test_structure_selection.py` and related tests.

**Interfaces:** Existing `select_source_excerpt(body, question, limit, *, focus_queries=None) -> SourceExcerpt` and `select_evidence_passages(...) -> tuple[EvidencePassage, ...]` unchanged. `strategy` distinguishes query/full/prefix/no_match/budget_omitted; ranges always address stored text.

- [x] 新增多实体干扰、ASCII 子串误匹配、邻接否定段、无命中、无代码中文、英文与不可分割长块回归。

```python
def test_query_does_not_return_unrelated_prefix():
    result = select_source_excerpt('Ordinary background.\n\n' * 100, 'quasar', 600)
    assert result.ranges == ()
    assert result.strategy == 'no_match'
```

- [x] 执行 `.venv/Scripts/python.exe -m pytest tests/tools/test_structured_retrieval.py -q`，观察相关性和无命中断言失败。
- [x] 代码标识符由问题提取，限定名匹配末段；共用模块前缀不成为主要实体。ASCII 按完整 token、中文仍按短词匹配。目标实体轮转选取完整段落及标题所属内容，已有 focus_queries 也轮转；之后才按普通相关度和原文位置补齐。

```python
# Every addition consumes the same rendered budget, never one budget per fact.
proposed = _merge([*selected, (start, end)])
if len(_render(body, proposed, newlines).text) <= limit:
    selected = proposed
```

- [x] 标题跟段落关联；长块按完整句/行分组，代码 fence 不拆为假完整内容；同节邻接组用剩余预算补入。长文无匹配/适配失败明确诊断，不前缀兜底；短正文全文、显式 start 和无 query 的兼容 prefix 保留。
- [x] 回放已保存真实正文的实际分支查询；必要时将原始 HTML 固定为检索回归夹具，模型研究输入不带金答案。执行 `tests/tools/test_structured_retrieval.py tests/tools/test_structure_selection.py tests/tools/test_evidence_views.py tests/strategies/test_structure_evaluation.py tests/responses/test_excerpts.py`。

## Task 3: 阅读完整组适配与三模式回归

**Files:** Modify `backend/src/deeptrace/tools/evidence_read.py`, `backend/src/deeptrace/harness/prompts.py`; reuse `backend/src/deeptrace/harness/research_findings.py` unless a newly demonstrated group-fit defect requires adjustment. Create `backend/tests/tools/test_structured_read_preview.py`.

**Interfaces:** Existing ReadEvidenceArguments, `_fit_preview(...) -> str`, short-reference numbering and capture_read_anchors remain compatible. Query selection diagnostics reach the tool's selection envelope; no-match produces no passage/reference/anchor.

- [x] 新增 JSON 转义超限不得截断最后一组、预算省略、无命中无 anchor、实际展示坐标和短编号兼容的失败测试。

```python
payload = json.loads(_fit_preview(record, body, passages, strategy='query'))
assert all(p['text'] == body[p['start']:p['end']] for p in payload['passages'])
assert payload['passages'] == []  # one entire escaped group cannot fit
assert payload['selection']['omitted'] is True
```

- [x] 执行 `.venv/Scripts/python.exe -m pytest tests/tools/test_structured_read_preview.py -q` 并确认组截断断言先失败。
- [x] query/full 按完整组适配 JSON，显式 find/range 保留有界窗口。完整组省略记 selection 诊断，不造 anchor。默认提示按问题选段；find 只定位已见字符串，不优先猜中文句子。
- [x] 执行新测试与 `tests/tools/test_evidence_read.py tests/tools/test_coherent_read_context.py tests/harness/test_read_anchors.py tests/harness/test_finish_research.py tests/integration/test_evidence_loop_modes.py`；随后完整 `.venv/Scripts/python.exe -m pytest -m 'not real' -q` 与独立评分环境回归。
- [x] 对变化模块运行 Ruff/compileall；按 code-review-and-quality 多轴自审，若发现实际回归先补失败测试再修复。

## Task 4: 一次性真实联网恢复验证

**Files:** Create preregistration/replay/summary scripts under `tmp/structured-retrieval-*`; create `docs/evaluation/structured-retrieval-validation-20261004.md`; update spec/plan status only after actual results.

- [x] 参照 `tmp/evidence-first-preflight.py` 用全新 prefix `structured-retrieval-answer-20261004`，核对模型、预算、数据/评分器/源码身份；保存 src/tests 和登记，不含 .env。新策略身份显式记录，旧 scorer/judge 保持一致。
- [x] 执行真实 live CLI：同题三模式各一次、Answer、12 轮；参数通过实际 `--help` 核对，运行/批次预算不变。执行状态失败也保存结果，不重复跑。
- [x] 使用 `.venv-ragas` 执行原 Ragas CLI、48 Provider 上限、一次评分；评分错误报 N/A 而非 0，不重评。
- [x] 新 summary 单列三模式 F1/Faithfulness/Goal、程序状态、指定来源、逐项内容验收、耗时、输入/输出/总 token、search/fetch/read、评分用量/缺失 usage；来源/引用字面审计不冒充语义验收。
- [x] 同旧主模式 0.80 参照和最近 0.60 结果比较；没有合格配对成功时不宣称成本改善。未过恢复门槛不扩大付费实验，保留真实错误供下一步定位。

## Plan self-review

提取、实体检索、完整组预览、授权/恢复兼容分别对应 Task 1–3；一次性联网和固定评分对应 Task 4。版本执行与 fetch/read 合并未被混入。本计划不引入新权限或缺失技能的假执行记录。
