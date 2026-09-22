# Agent Harness Content and Interview Materials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Field Notes-style DeepResearch Agent Harness article, a practical learning/interview guide, an implementation-gap ledger, six maintainable SVG diagrams, and concise README/resume derivatives.

**Architecture:** Treat the repository source and tests as the factual layer, the gap ledger as the claim-to-evidence boundary, the long article as the narrative layer, and README/resume content as downstream summaries. Build and verify the evidence ledger and diagrams before writing the narrative so every claim and visual has a stable source.

**Tech Stack:** Markdown, SVG 1.1, PowerShell validation, Python/LangGraph/FastAPI source references, Pytest, React/Vite/Vitest.

**Spec:** `docs/superpowers/specs/2026-09-22-agent-harness-content-design.md`

## Global Constraints

- The reference WeChat article is a style and structure reference only; do not copy its business scenario, claims, prose, or images.
- The primary audience is Agent development and LLM application engineering candidates and interviewers.
- Describe the coherent final architecture in the main article without roadmap labels interrupting the narrative.
- Put implementation status and missing work in the separate gap ledger.
- Never invent benchmark counts, business outcomes, latency, cost, completion rate, or improvement percentages.
- Clearly separate deterministic/offline verification, Showcase fixture data, real-provider runs, and real-world outcomes.
- Use project-native SVG for diagrams; do not use generated raster images for architecture diagrams.
- Preserve all pre-existing uncommitted changes. In particular, `docs/README.md` and `docs/resume/README.md` are already dirty and must not be staged or committed with user-owned edits.
- Stage explicit paths only; never use `git add .` or `git add -A`.

---

## File Structure

### New files

- `docs/resume/Agent Harness项目深度拆解.md` — long Field Notes-style project article.
- `docs/resume/Agent Harness学习与面试路线.md` — staged learning path, exercises, completion criteria, and interview evidence checklist.
- `docs/resume/Agent Harness实现差距与完善清单.md` — claim-to-code status ledger and prioritized completion plan.
- `docs/assets/harness-five-core-problems.svg` — five-part Harness mental model.
- `docs/assets/harness-research-loop.svg` — request-to-Outcome execution loop.
- `docs/assets/harness-context-assembly.svg` — layered context assembly and trimming.
- `docs/assets/harness-failure-ownership.svg` — transport, semantic, and recovery failure ownership.
- `docs/assets/harness-data-ownership.svg` — State, Evidence, Ledger, and Memory ownership.
- `docs/assets/harness-learning-interview-roadmap.svg` — read, modify, verify, and explain progression.

### Modified files

- `README.md` — concise links and positioning for the new material.
- `docs/resume/多模式深度研究Agent简历项目材料.md` — Agent-development resume version and interview introductions.
- `docs/README.md` — documentation index links; preserve existing uncommitted evaluation and comparison links.
- `docs/resume/README.md` — resume/learning index links; preserve the existing uncommitted comparison link.

### Unchanged supporting files

- `docs/architecture/agent-harness.md` remains the technical source of truth and is linked rather than duplicated.
- `docs/resume/Agent Harness面试手册.md` remains the detailed Q&A collection.
- `docs/resume/Agent Harness源码学习指南.md` remains the source-reading reference and is linked from the new learning route.

---

### Task 1: Establish the Current Evidence Baseline and Gap Ledger

**Files:**
- Create: `docs/resume/Agent Harness实现差距与完善清单.md`
- Read: `backend/src/deeptrace/harness/`
- Read: `backend/src/deeptrace/tools/`
- Read: `backend/src/deeptrace/persistence/`
- Read: `backend/src/deeptrace/strategies/`
- Read: `backend/tests/harness/`, `backend/tests/tools/`, `backend/tests/integration/`, `backend/tests/eval/`

**Interfaces:**
- Consumes: current source tree, deterministic tests, the approved design spec.
- Produces: the exact status vocabulary and evidence links consumed by Tasks 4–7.

- [ ] **Step 1: Capture the protected working-tree state**

Run:

```powershell
git status --short
git diff -- docs/README.md docs/resume/README.md
```

Expected: the two index files show pre-existing additions; save the output in the task notes and do not stage either file.

- [ ] **Step 2: Run the deterministic backend baseline**

Run:

```powershell
Set-Location backend
uv run pytest -m "not real" -q
Set-Location ..
```

Expected: the suite completes without invoking real credentials. Record the exact pass/deselect/fail counts from this run; do not reuse the older `464 passed, 1 deselected` number if it has changed.

- [ ] **Step 3: Audit each article capability against source and tests**

Use `rg` to trace the concrete implementation before writing status rows:

```powershell
rg -n "class AgentOutcome|prepare_context|completion_nudge|ToolMessage|ModelGateway" backend/src backend/tests
rg -n "checkpoint|ledger|singleflight|budget|Evidence|memory" backend/src backend/tests
rg -n "Workflow|PlanExecute|MultiAgent|strategy" backend/src/deeptrace/strategies backend/tests/strategies
rg -n "eval|judge|dataset|fault" backend/src/deeptrace/eval backend/tests/eval backend/tests/integration
```

Expected: every gap-ledger row has at least one specific source or test path, or explicitly states that no implementation evidence exists.

- [ ] **Step 4: Write the gap ledger using one fixed schema**

Use this document structure and status vocabulary:

```markdown
# Agent Harness 实现差距与完善清单

## 阅读说明

- `已实现`：源码和确定性测试均能验证核心行为。
- `部分实现`：主链路存在，但完整方案中的边界、故障或评测仍有缺口。
- `尚未实现`：当前只有设计或接口，没有可验证的运行路径。

## 能力总览

| 能力 | 当前状态 | 代码证据 | 主要缺口 | 推荐方案 | 验收方法 | 优先级 |
| --- | --- | --- | --- | --- | --- | --- |

## 面试前必须补齐

## 重要但可分阶段完成

## 可选增强

## 本次验证记录
```

Include rows for Shared Agent Loop, context invariants, complete tool-call pairing, ModelGateway, ToolGateway, URL/SSRF validation, budgets, bounded concurrency, Evidence Store, citations, Checkpoint, Ledger replay, three retry owners, AgentOutcome, memory lifecycle, three strategies, distributed runtime, offline eval, real-provider eval, tenant isolation, HITL approval, prompt-injection defense, and precise token accounting.

- [ ] **Step 5: Validate the ledger contains no unsupported result language**

Run:

```powershell
rg -n "提升了|降低了|通过率|成本下降|线上效果|真实收益" 'docs/resume/Agent Harness实现差距与完善清单.md'
rg -n "已实现|部分实现|尚未实现" 'docs/resume/Agent Harness实现差距与完善清单.md'
```

Expected: any result claim is accompanied by the exact validation command or result; every capability uses one of the three approved statuses.

- [ ] **Step 6: Commit only the new ledger**

```powershell
git add -- 'docs/resume/Agent Harness实现差距与完善清单.md'
git diff --cached --check
git commit -m "docs: map agent harness capabilities to implementation"
```

---

### Task 2: Create the Core Harness Learning and Runtime SVGs

**Files:**
- Create: `docs/assets/harness-five-core-problems.svg`
- Create: `docs/assets/harness-research-loop.svg`
- Create: `docs/assets/harness-context-assembly.svg`

**Interfaces:**
- Consumes: Field Notes palette and terminology from the spec and Task 1.
- Produces: three self-contained SVGs embedded by the main article and learning guide.

- [ ] **Step 1: Prove the asset check fails before creation**

Run:

```powershell
$assets = @(
  'docs/assets/harness-five-core-problems.svg',
  'docs/assets/harness-research-loop.svg',
  'docs/assets/harness-context-assembly.svg'
)
$missing = $assets | Where-Object { -not (Test-Path $_) }
if ($missing.Count -eq 0) { throw 'Expected assets to be missing before Task 2' }
$missing
```

Expected: all three paths are reported missing.

- [ ] **Step 2: Implement the shared visual language in each SVG**

Use `viewBox="0 0 1600 900"`, a warm `#F2EDE3` background, ink `#243236`, copper `#B66932`, verified green `#5D9E8D`, failure brown `#785147`, and border `#CBBDA8`. Each file must include `<title>` and `<desc>`, use only local/system fonts, keep body text at least 22 px, and avoid external resources.

The first diagram must show exactly five connected modules:

```text
Agent Loop → Context → Tool → Runtime → Eval
   ↑                                      ↓
   └──────────── feedback / evidence ─────┘
```

The second diagram must show:

```text
ResearchInput → prepare_context → ModelGateway → decision
                                      ├─ tool calls → ToolGateway → Evidence
                                      └─ no calls ────────────────┐
Evidence / answer → observe → Execution Policy → continue or AgentOutcome
```

The third diagram must show stable, task, working, and evidence layers entering the model view, plus full tool-exchange trimming and reserved output space.

- [ ] **Step 3: Parse every SVG as XML**

Run:

```powershell
Get-ChildItem docs/assets/harness-five-core-problems.svg,docs/assets/harness-research-loop.svg,docs/assets/harness-context-assembly.svg |
  ForEach-Object { [xml](Get-Content -Raw $_.FullName) | Out-Null }
```

Expected: no XML parser exception.

- [ ] **Step 4: Inspect each SVG visually**

Open each SVG in the Codex file preview and verify: no cropped text, no overlapping arrows, readable labels at fit-to-window scale, and consistent arrow semantics. Fix the SVG and repeat until all three pass.

- [ ] **Step 5: Commit the core diagrams**

```powershell
git add -- docs/assets/harness-five-core-problems.svg docs/assets/harness-research-loop.svg docs/assets/harness-context-assembly.svg
git diff --cached --check
git commit -m "docs: add core agent harness diagrams"
```

---

### Task 3: Create Reliability, Data Ownership, and Interview Roadmap SVGs

**Files:**
- Create: `docs/assets/harness-failure-ownership.svg`
- Create: `docs/assets/harness-data-ownership.svg`
- Create: `docs/assets/harness-learning-interview-roadmap.svg`

**Interfaces:**
- Consumes: the palette and diagram semantics from Task 2; status decisions from Task 1.
- Produces: the reliability visuals for the main article and the learning visual for the companion guide.

- [ ] **Step 1: Prove the second asset set is missing**

```powershell
$assets = @(
  'docs/assets/harness-failure-ownership.svg',
  'docs/assets/harness-data-ownership.svg',
  'docs/assets/harness-learning-interview-roadmap.svg'
)
$missing = $assets | Where-Object { -not (Test-Path $_) }
if ($missing.Count -eq 0) { throw 'Expected assets to be missing before Task 3' }
$missing
```

Expected: all three paths are reported missing.

- [ ] **Step 2: Draw failure ownership without collapsing the retry layers**

The diagram must show these exact owners and boundaries:

```text
Transport retry  → ModelGateway / ToolGateway → timeout, connection, rate limit
Semantic repair  → Shared Agent Loop          → query, argument, or source correction
Recovery replay  → Checkpoint / Worker / Ledger → crash and at-least-once replay
```

Add a bottom warning strip: “同一失败只能有一个主要重试所有者；外部副作用先核对，再决定重放。”

- [ ] **Step 3: Draw data ownership as four stores with explicit payloads**

The diagram must distinguish:

```text
State / Checkpoint: serializable control state, messages, todos, evidence IDs, outcome
Evidence Store: page body, source metadata, content hash
Execution Ledger: call identity, committed result, replay decision
Memory Store: validated cross-session facts and preferences
```

Show Runtime Context outside the persistent stores and label it “model, tools, clock, connections; not checkpointed.”

- [ ] **Step 4: Draw the learning-to-interview roadmap**

Use four stages—读懂、修改、验证、表达—and attach one concrete artifact to each: call-chain diagram, branch/fault patch, Trace/Test/Eval report, and resume sentence/interview answer.

- [ ] **Step 5: Parse and visually inspect all three SVGs**

Run:

```powershell
Get-ChildItem docs/assets/harness-failure-ownership.svg,docs/assets/harness-data-ownership.svg,docs/assets/harness-learning-interview-roadmap.svg |
  ForEach-Object { [xml](Get-Content -Raw $_.FullName) | Out-Null }
```

Then preview each file and verify the same readability criteria used in Task 2.

- [ ] **Step 6: Commit the reliability and learning diagrams**

```powershell
git add -- docs/assets/harness-failure-ownership.svg docs/assets/harness-data-ownership.svg docs/assets/harness-learning-interview-roadmap.svg
git diff --cached --check
git commit -m "docs: add harness reliability and learning diagrams"
```

---

### Task 4: Write the Long Field Notes-Style Project Article

**Files:**
- Create: `docs/resume/Agent Harness项目深度拆解.md`
- Reference: `docs/resume/Agent Harness实现差距与完善清单.md`
- Reference: `docs/architecture/agent-harness.md`
- Reference: `docs/assets/deepresearch-workbench.png`
- Reference: all six new SVGs

**Interfaces:**
- Consumes: verified claims from Task 1 and visuals from Tasks 2–3.
- Produces: the canonical narrative consumed by README and resume summaries.

- [ ] **Step 1: Create the article skeleton with all 11 Field Notes**

Use this exact high-level structure:

```markdown
# DeepResearch Agent Harness，简历怎么写出工程深度？

> 项目定位与事实说明

开场：今年 Agent 项目为什么必须回答“端到端完成了什么复杂任务”

![DeepResearch 工作台](../assets/deepresearch-workbench.png)

AGENT FIELD NOTE 01 / 11
## 复杂研究任务：为什么“搜索 + 总结”还不够

...

AGENT FIELD NOTE 11 / 11
## 最终简历：把系统设计压成可追问的项目经历
```

Use the eleven subjects approved in the spec. Target 7,000–10,000 Chinese characters so each section is substantive but remains scannable.

- [ ] **Step 2: Write the task story and system thesis**

Frame the end-to-end task as: receive a complex open question with constraints, select an orchestration strategy, search and fetch primary evidence, repair gaps, produce a cited answer, and return a structured outcome under bounded budget and recoverable execution.

Use this central thesis verbatim:

```markdown
**真正的 Agent Harness，不是让模型多调用几次工具，而是把模型的判断变成可恢复、可审计、可验收的研究过程。**
```

- [ ] **Step 3: Write the engineering sections against concrete project boundaries**

For each Field Note, include at least one source link and one of `简历怎么写`、`面试追问`、`怎么验证`. Link to project files with repository-relative Markdown paths. Avoid claiming that the plan is a dependency DAG, that local reservation guarantees remote hard limits, or that Checkpoint alone guarantees exactly-once behavior.

- [ ] **Step 4: Embed diagrams at the point where they answer the section question**

Use these exact relative paths:

```markdown
![Agent Harness 的五个核心问题](../assets/harness-five-core-problems.svg)
![一次研究请求的完整执行闭环](../assets/harness-research-loop.svg)
![围绕当前决策装配 Context](../assets/harness-context-assembly.svg)
![三类失败与重试所有权](../assets/harness-failure-ownership.svg)
![State、Evidence、Ledger 与 Memory 的数据边界](../assets/harness-data-ownership.svg)
```

Do not embed the learning roadmap in the main article; reserve it for Task 5.

- [ ] **Step 5: Write the final resume block without fabricated metrics**

Include project title, date range, technology stack, one paragraph, and five bullets: Shared Agent Loop, Context, Tool Governance, Reliability, and Evaluation/Evidence. For results, report only the exact deterministic test baseline from Task 1 and clearly label it as offline verification.

- [ ] **Step 6: Verify structure, links, and forbidden carry-over**

Run:

```powershell
$article='docs/resume/Agent Harness项目深度拆解.md'
(rg -c '^AGENT FIELD NOTE [0-9]{2} / 11$' $article)
rg -n '跨境|店铺|广告预算|ROAS|新品首周' $article
$markers = @('下一阶段','未来计划',('T'+'BD'),('T'+'ODO'),('['+'N'+']'),('['+'M'+']'),'A→B')
Select-String -Path $article -Pattern $markers
```

Expected: Field Note count is 11; the two forbidden-content searches return no matches.

- [ ] **Step 7: Commit the main article**

```powershell
git add -- 'docs/resume/Agent Harness项目深度拆解.md'
git diff --cached --check
git commit -m "docs: add deepresearch agent harness field notes"
```

---

### Task 5: Write the Harness Learning and Interview Route

**Files:**
- Create: `docs/resume/Agent Harness学习与面试路线.md`
- Reference: `docs/resume/Agent Harness源码学习指南.md`
- Reference: `docs/resume/Agent Harness面试手册.md`
- Reference: `docs/resume/Agent Harness实现差距与完善清单.md`
- Reference: `docs/assets/harness-learning-interview-roadmap.svg`

**Interfaces:**
- Consumes: source map, gap ledger, and existing detailed learning/interview documents.
- Produces: an action-oriented path that links to, rather than duplicates, the detailed guides.

- [ ] **Step 1: Write the five-stage learning structure**

Use this exact section pattern for Agent Loop, Context, Tool, Runtime, and Eval:

```markdown
## 阶段一：Agent Loop

### 学习目标
### 推荐源码顺序
### 必做实验
### 完成标准
### 面试追问
### 应准备的证据
```

Each stage must name exact files and at least one executable test command.

- [ ] **Step 2: Define concrete experiments and completion criteria**

Require these experiments:

- trace one request from Session Graph through strategy routing to `AgentOutcome`;
- force an early model finish and observe the bounded completion nudge;
- construct a context-pressure case and verify instruction/task/constraints survive trimming;
- trigger invalid tool arguments and verify a paired failure `ToolMessage`;
- compare independent parallel calls with a search-dependent fetch;
- inject transport failure, semantic failure, and recovery replay separately;
- compare Workflow, Plan-and-Execute, and Multi-Agent under fixed input and budget.

Completion criteria must use observable artifacts: a trace, passing test, before/after context envelope, persisted Evidence ID, or evaluation report.

- [ ] **Step 3: Add the interview preparation layer**

Include 30-second, 3-minute, and deep-dive preparation goals; link detailed answers to `Agent Harness面试手册.md`; include a final checklist for two divergent traces, one failure recovery, one context experiment, one evaluation report, and one live/no-key demo.

- [ ] **Step 4: Embed the roadmap and verify no duplication**

Embed:

```markdown
![从读懂 Harness 到能够面试](../assets/harness-learning-interview-roadmap.svg)
```

Check that long Q&A answers and the full source-reading sequence remain in the existing dedicated documents instead of being copied wholesale.

- [ ] **Step 5: Validate required sections and links**

```powershell
$guide='docs/resume/Agent Harness学习与面试路线.md'
rg -n '^## 阶段[一二三四五]：' $guide
rg -n '^### (学习目标|推荐源码顺序|必做实验|完成标准|面试追问|应准备的证据)$' $guide
Test-Path 'docs/assets/harness-learning-interview-roadmap.svg'
Test-Path 'docs/resume/Agent Harness面试手册.md'
Test-Path 'docs/resume/Agent Harness源码学习指南.md'
```

Expected: five stages exist, each required subsection appears five times, and all linked files exist.

- [ ] **Step 6: Commit the learning route**

```powershell
git add -- 'docs/resume/Agent Harness学习与面试路线.md'
git diff --cached --check
git commit -m "docs: add agent harness learning and interview route"
```

---

### Task 6: Derive the Resume Material and Root README

**Files:**
- Modify: `docs/resume/多模式深度研究Agent简历项目材料.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: canonical claims from Tasks 1 and 4.
- Produces: concise recruiter-facing and repository-facing entry points.

- [ ] **Step 1: Rewrite the recommended resume version for Agent development roles**

Keep the existing document title, then provide:

- project title, ownership, dates, and verified technology stack;
- one 70–120 Chinese-character project description;
- five bullets named `Shared Agent Loop`, `Context 工程`, `Tool 治理`, `稳定性与恢复`, and `Evidence 与 Eval`;
- an offline-verification line containing only the Task 1 result;
- a three-bullet compact version;
- 30-second, 3-minute, and deep-dive introductions;
- factual boundaries and links to the long article, learning route, gap ledger, and interview handbook.

- [ ] **Step 2: Add a concise “学习与面试材料” entry to the root README**

Place it after `源码导览`. Use a compact table linking the four documents:

```markdown
## 学习与面试材料

| 材料 | 适合用途 |
| --- | --- |
| [项目深度拆解](docs/resume/Agent%20Harness项目深度拆解.md) | 从复杂任务到 Harness 设计和简历表达 |
| [学习与面试路线](docs/resume/Agent%20Harness学习与面试路线.md) | 按阶段读源码、做实验并准备证据 |
| [实现差距与完善清单](docs/resume/Agent%20Harness实现差距与完善清单.md) | 区分完整方案与当前实现 |
| [面试手册](docs/resume/Agent%20Harness面试手册.md) | 高频追问和压力追问 |
```

- [ ] **Step 3: Reconcile the test baseline in both files**

Replace stale counts only when Task 1 produced a different deterministic result. Do not state real-provider success if real tests were not run.

- [ ] **Step 4: Validate compactness and local links**

```powershell
rg -n '^## |^### ' 'docs/resume/多模式深度研究Agent简历项目材料.md' README.md
Test-Path 'docs/resume/Agent Harness项目深度拆解.md'
Test-Path 'docs/resume/Agent Harness学习与面试路线.md'
Test-Path 'docs/resume/Agent Harness实现差距与完善清单.md'
```

Expected: all destinations exist; README does not duplicate Field Note prose.

- [ ] **Step 5: Commit only the two clean target files**

```powershell
git add -- README.md 'docs/resume/多模式深度研究Agent简历项目材料.md'
git diff --cached --check
git commit -m "docs: align readme and resume for agent roles"
```

---

### Task 7: Update the Documentation Indexes Without Absorbing User Changes

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/resume/README.md`

**Interfaces:**
- Consumes: all completed artifacts.
- Produces: discoverable documentation navigation while preserving pre-existing dirty hunks.

- [ ] **Step 1: Re-read the pre-existing diffs before editing**

```powershell
git diff -- docs/README.md docs/resume/README.md
```

Expected: the existing evaluation-plan and open-source-comparison additions are still present.

- [ ] **Step 2: Add the three new documents to both indexes**

In `docs/README.md`, add links under `求职与学习`. In `docs/resume/README.md`, extend the table and change the recommended reading order to:

```text
项目深度拆解 → 学习与面试路线 → 源码学习指南 → 实现差距与完善清单 → 面试手册
```

Preserve every pre-existing line, including the evaluation plan and open-source comparison entries.

- [ ] **Step 3: Verify the combined diff is additive and intentional**

```powershell
git diff -- docs/README.md docs/resume/README.md
```

Expected: no previously added line is removed or rewritten unintentionally.

- [ ] **Step 4: Do not stage or commit these two dirty files**

Leave both files modified in the working tree. Report clearly that their final diff contains both pre-existing user changes and the new index links, so no user-owned content was committed without permission.

---

### Task 8: Run Final Content, Asset, and Project Verification

**Files:**
- Verify: all files created or modified in Tasks 1–7.
- Modify only if validation reveals a defect in those files.

**Interfaces:**
- Consumes: complete artifact set.
- Produces: verified deliverables and a concise final report.

- [ ] **Step 1: Verify all deliverables exist**

```powershell
$required = @(
  'docs/resume/Agent Harness项目深度拆解.md',
  'docs/resume/Agent Harness学习与面试路线.md',
  'docs/resume/Agent Harness实现差距与完善清单.md',
  'docs/assets/harness-five-core-problems.svg',
  'docs/assets/harness-research-loop.svg',
  'docs/assets/harness-context-assembly.svg',
  'docs/assets/harness-failure-ownership.svg',
  'docs/assets/harness-data-ownership.svg',
  'docs/assets/harness-learning-interview-roadmap.svg'
)
$missing = $required | Where-Object { -not (Test-Path $_) }
if ($missing) { throw "Missing deliverables: $($missing -join ', ')" }
```

Expected: no missing files.

- [ ] **Step 2: Parse all SVGs and search all new prose for placeholders**

```powershell
Get-ChildItem docs/assets/harness-*.svg | ForEach-Object { [xml](Get-Content -Raw $_.FullName) | Out-Null }
$markers = @(('T'+'BD'),('T'+'ODO'),('['+'N'+']'),('['+'M'+']'),'A→B','通过数／总数','实测值')
Get-ChildItem docs/resume -Filter *.md | Select-String -Pattern $markers
Select-String -Path README.md -Pattern $markers
```

Expected: SVG parsing succeeds and no unfinished placeholder remains in changed deliverables.

- [ ] **Step 3: Validate exact local asset and document paths**

```powershell
$paths = @(
  'docs/assets/deepresearch-workbench.png',
  'docs/assets/harness-five-core-problems.svg',
  'docs/assets/harness-research-loop.svg',
  'docs/assets/harness-context-assembly.svg',
  'docs/assets/harness-failure-ownership.svg',
  'docs/assets/harness-data-ownership.svg',
  'docs/assets/harness-learning-interview-roadmap.svg',
  'docs/resume/Agent Harness项目深度拆解.md',
  'docs/resume/Agent Harness学习与面试路线.md',
  'docs/resume/Agent Harness实现差距与完善清单.md',
  'docs/resume/Agent Harness面试手册.md',
  'docs/resume/Agent Harness源码学习指南.md'
)
$paths | ForEach-Object { if (-not (Test-Path $_)) { throw "Broken local path: $_" } }
```

Expected: every path resolves.

- [ ] **Step 4: Re-run deterministic backend verification**

```powershell
Set-Location backend
uv run pytest -m "not real" -q
Set-Location ..
```

Expected: result matches the baseline recorded in Task 1 or any difference is investigated and the documents are corrected.

- [ ] **Step 5: Verify frontend commands documented in README**

```powershell
Set-Location frontend
npm run lint
npm test
npm run build
npm run build:showcase
Set-Location ..
```

Expected: all four commands succeed.

- [ ] **Step 6: Review every SVG and both long documents in rendered form**

Open all six SVGs and the Markdown previews. Confirm hierarchy, captions, line wrapping, link rendering, image sizing, and Chinese typography. Fix any defect and repeat the relevant validation.

- [ ] **Step 7: Review factual consistency across all derivatives**

Compare the main article, gap ledger, resume material, root README, and architecture document. Verify that terminology, test counts, strategy boundaries, retry ownership, and current limitations do not contradict one another.

- [ ] **Step 8: Commit only final fixes to otherwise clean deliverables**

Stage explicit fixed files only. Do not stage `docs/README.md` or `docs/resume/README.md` because they contain pre-existing user changes.

```powershell
git diff --check
git status --short
```

Expected: the only intentionally uncommitted content is the protected pre-existing work plus the two combined index-file edits described in Task 7.

---

## Final Handoff

Report:

- the three new document paths and six SVG paths;
- the actual backend and frontend verification results;
- which claims remain `部分实现` or `尚未实现` in the gap ledger;
- that the two dirty index files were preserved and intentionally not committed;
- the commits created for new/clean deliverables;
- a recommended reading order beginning with the long article and ending with the interview handbook.
