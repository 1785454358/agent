# DeepResearch Differentiation Interview Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create one focused Chinese learning/interview guide that answers how this DeepResearch differs from mature alternatives, supports progressive follow-up questions, and teaches the candidate how to prepare evidence without fabricating implementation claims.

**Architecture:** Use one canonical positioning statement as the source for 30-second, 90-second, and 5-minute answers. Expand it through five differentiation dimensions, three named competitor follow-ups, a pressure-question chain, safe-expression guidance, and an evidence-oriented practice plan; link existing detailed documents instead of duplicating them.

**Tech Stack:** Markdown, repository-relative links, PowerShell content validation.

**Spec:** `docs/superpowers/specs/2026-09-27-deepresearch-differentiation-interview-guide-design.md`

## Global Constraints

- Use the posture “acknowledge mature-project strengths first, then establish a different evaluation axis.”
- Do not claim the project has better research quality without a same-protocol benchmark.
- Do not invent benchmark scores, online benefits, production maturity, or completed implementation evidence.
- The main distinction is a governed Agent Runtime: strategy/runtime separation, explicit state ownership, failure semantics, evidence/outcome contracts, and process-aware evaluation.
- Use generic mature DeepResearch as the main comparison, then add focused follow-ups for Tongyi DeepResearch, LangChain open_deep_research, and gpt-researcher.
- Keep the new guide focused on one mother question; link rather than copy existing comparison, interview, learning, and gap documents.
- Preserve all pre-existing uncommitted changes. `docs/README.md` and `docs/resume/README.md` are dirty and must not be staged or committed.
- Stage explicit paths only; never use `git add .` or `git add -A`.

---

## File Structure

### New file

- `docs/resume/DeepResearch核心差异面试与学习手册.md` — canonical answer, named comparisons, pressure questions, wording boundaries, learning tasks, mock interview, and scoring rubric.

### Modified files

- `docs/README.md` — add one navigation entry while preserving existing uncommitted content.
- `docs/resume/README.md` — add one table row and include the new guide in the reading order while preserving existing uncommitted content.

### Referenced files

- `docs/resume/开源项目对比面试问答.md` — detailed competitor notes.
- `docs/resume/Agent Harness面试手册.md` — internal Harness technical questions.
- `docs/resume/Agent Harness学习与面试路线.md` — full source-learning and experiment route.
- `docs/resume/Agent Harness实现差距与完善清单.md` — implementation status and evidence boundary.

---

### Task 1: Write the Canonical Positioning and Progressive Answers

**Files:**
- Create: `docs/resume/DeepResearch核心差异面试与学习手册.md`
- Read: `docs/resume/开源项目对比面试问答.md`
- Read: `docs/resume/Agent Harness面试手册.md`
- Read: `docs/resume/Agent Harness实现差距与完善清单.md`

**Interfaces:**
- Consumes: the approved central positioning and factual-expression boundaries.
- Produces: one stable thesis reused by all later answers and follow-ups.

- [ ] **Step 1: Verify the target file does not already exist**

Run:

```powershell
if (Test-Path 'docs/resume/DeepResearch核心差异面试与学习手册.md') {
  throw 'Target document already exists; inspect before overwriting.'
}
```

Expected: command completes without output.

- [ ] **Step 2: Create the mother-question framing and answer formula**

Start the document with:

```markdown
# DeepResearch 核心差异：面试主问题与学习手册

## 母问题

> 你做的 DeepResearch 和市面上成熟的 DeepResearch 项目，核心区别是什么？

## 面试官真正想判断什么

## 统一答题公式

承认对方优势 → 说明目标不同 → 给出三项结构差异 → 提供一个工程例子 → 主动收住事实边界
```

Explain that the interviewer is testing competitor awareness, independent design judgment, evidence depth, and honesty—not asking for a feature checklist.

- [ ] **Step 3: Write the canonical positioning paragraph**

Use this thesis verbatim once, then paraphrase it consistently elsewhere:

```markdown
成熟 DeepResearch 项目主要竞争“研究结果做得多好”，我的项目更关注“开放式研究过程如何在真实工程环境中受控运行”。我不声称模型能力天然比它们强，差异在于把策略、上下文、工具、副作用、恢复、证据和退出统一成可验证的 Harness 协议。
```

- [ ] **Step 4: Write a 30-second answer**

The answer must contain exactly four moves: acknowledge mature projects, state the different goal, name three differences (`受控`, `可恢复`, `可验证`), and close with the quality boundary. Target 120–180 Chinese characters so it can be spoken without rushing.

- [ ] **Step 5: Write a 90-second answer**

The answer must cover:

1. mature projects are stronger in model/data/ecosystem/product maturity;
2. this project separates strategy orchestration from a shared runtime;
3. Evidence/Outcome/Checkpoint/Ledger are first-class objects;
4. evaluation includes process, failure, and side effects;
5. no claim of superior answer quality without same-protocol evaluation.

- [ ] **Step 6: Write a 5-minute answer with one running failure example**

Use “a page fetch or provider call completes but the response is lost” as the running example. Walk through Context, ToolGateway, stable call identity, Checkpoint, Ledger, Evidence, Execution Policy, and AgentOutcome. End by explaining why this is a different engineering axis rather than a claim of universal superiority.

- [ ] **Step 7: Validate the three answers share the same thesis**

Run:

```powershell
$doc='docs/resume/DeepResearch核心差异面试与学习手册.md'
rg -n '^## (30 秒回答|90 秒回答|5 分钟回答)$' $doc
rg -n '受控|可恢复|可验证|不声称|研究质量' $doc
```

Expected: all three answer headings exist; the boundary language appears in the document.

---

### Task 2: Add Differentiators, Named Comparisons, and Pressure Questions

**Files:**
- Modify: `docs/resume/DeepResearch核心差异面试与学习手册.md`

**Interfaces:**
- Consumes: the canonical thesis from Task 1.
- Produces: deeper technical branches that remain consistent with the short answers.

- [ ] **Step 1: Add five differentiation sections using one repeated schema**

Create sections for:

1. 目标坐标：答案质量/开箱即用 vs 受治理运行时；
2. 架构分层：策略编排 vs Shared Harness；
3. 状态所有权：最终文本 vs Evidence/Outcome/Checkpoint/Ledger；
4. 失败语义：简单重试 vs transport/semantic/recovery owners；
5. 评测范围：答案评分 vs quality/cost/termination/recovery/side effects。

Each section must include these subheadings:

```markdown
### 成熟项目常见做法
### 我的选择
### 为什么值得做
### 代价与边界
### 面试一句话
### 要准备的证据
```

- [ ] **Step 2: Add three named competitor follow-ups**

For each competitor, use this order: strongest acknowledged advantage, different project objective, two concrete architectural differences, what to learn from it, and one boundary statement.

Required focus:

- Tongyi DeepResearch: trained model/data/benchmark strength vs runtime governance;
- LangChain open_deep_research: mature template/configurability/experimentation vs shared governance protocol;
- gpt-researcher: product completeness and fixed pipeline vs recoverable/auditable Harness.

Avoid version-specific implementation claims or numerical benchmark claims unless re-verified from primary sources during implementation.

- [ ] **Step 3: Write at least nine pressure questions with direct answers**

Include these exact questions:

```markdown
### 你的答案质量凭什么更好？
### 这是不是过度工程？
### LangGraph 已经有 Checkpoint，你还做了什么？
### 三种策略是不是为了堆功能？
### 这些亮点哪些真正实现了？
### 如果删掉 LangGraph，还剩下什么？
### 如果重做，最先砍掉什么？
### 为什么成熟项目没有这些设计？
### 运行时治理会不会拖慢研究质量和速度？
```

Every answer must: answer directly in the first sentence, name a trade-off, and close with evidence or a boundary.

- [ ] **Step 4: Add the strong-but-safe expression table**

Write at least eight rows covering research quality, Prompt Injection, exactly-once, offline tests, production maturity, strategy count, token cost, and evaluation. Use columns:

```markdown
| 推荐说法 | 容易翻车的说法 | 被追问后的收口 |
| --- | --- | --- |
```

- [ ] **Step 5: Validate structural coverage**

Run:

```powershell
$doc='docs/resume/DeepResearch核心差异面试与学习手册.md'
(rg -c '^## 差异 [1-5]：' $doc)
(rg -c '^## 点名追问：' $doc)
(rg -c '^### .*\？$' $doc)
```

Expected: five difference sections, three named-comparison sections, and at least nine question headings.

---

### Task 3: Add the Learning Route, Mock Interview, and Cross-Document Links

**Files:**
- Modify: `docs/resume/DeepResearch核心差异面试与学习手册.md`
- Reference: `docs/resume/Agent Harness学习与面试路线.md`
- Reference: `docs/resume/Agent Harness实现差距与完善清单.md`
- Reference: `docs/resume/Agent Harness面试手册.md`
- Reference: `docs/resume/开源项目对比面试问答.md`

**Interfaces:**
- Consumes: the five differences and pressure branches from Task 2.
- Produces: concrete study tasks and a repeatable interview rehearsal.

- [ ] **Step 1: Add one study card for each difference**

Each card must specify:

- one concept to understand;
- one existing document to read;
- one diagram/Trace/test/evaluation artifact to prepare;
- one basic question;
- one pressure question;
- one pass criterion stated as observable behavior.

- [ ] **Step 2: Add a 15–20 minute mock interview script**

Use this sequence:

```text
0–2 min   mother question and 90-second answer
2–5 min   competitor awareness and named comparison
5–9 min   one runtime failure example
9–13 min  evidence and evaluation challenge
13–16 min implementation-truth challenge
16–20 min redesign and trade-off reflection
```

Include interviewer prompts and the expected answer objective for each stage; do not write a second full answer script that duplicates earlier sections.

- [ ] **Step 3: Add a 30-point scoring rubric**

Use six dimensions worth five points each: positioning clarity, technical depth, trade-off awareness, evidence awareness, truth boundary, and speaking rhythm. Define observable criteria for scores 1, 3, and 5 in every dimension.

- [ ] **Step 4: Add navigation to existing detailed material**

Link to the four referenced documents and explain when to use each. Do not copy more than one short paragraph from any existing guide.

- [ ] **Step 5: Add a final rehearsal checklist**

Require: 30-second answer, 90-second answer, one failure Trace, one architecture diagram, one comparison example, one evaluation result, three honest limitations, and one redesign choice.

- [ ] **Step 6: Validate links and learning coverage**

Run:

```powershell
$doc='docs/resume/DeepResearch核心差异面试与学习手册.md'
rg -n '^## (学习训练|模拟面试|30 分评分表|面试前检查清单)$' $doc
Test-Path 'docs/resume/开源项目对比面试问答.md'
Test-Path 'docs/resume/Agent Harness面试手册.md'
Test-Path 'docs/resume/Agent Harness学习与面试路线.md'
Test-Path 'docs/resume/Agent Harness实现差距与完善清单.md'
```

Expected: all learning sections and referenced files exist.

- [ ] **Step 7: Commit only the new guide**

```powershell
git add -- 'docs/resume/DeepResearch核心差异面试与学习手册.md'
git diff --cached --check
git commit -m "docs: add deepresearch differentiation interview guide"
```

---

### Task 4: Add Index Entries Without Absorbing User Changes

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/resume/README.md`

**Interfaces:**
- Consumes: the completed guide from Tasks 1–3.
- Produces: discoverable navigation while preserving existing uncommitted edits.

- [ ] **Step 1: Capture the current index diffs before editing**

```powershell
git diff -- docs/README.md docs/resume/README.md
```

Expected: both files already contain uncommitted content that must remain intact.

- [ ] **Step 2: Add one concise entry to each index**

Use this description:

```text
DeepResearch 核心差异面试与学习手册：围绕“与成熟项目有什么不同”训练 30 秒、90 秒、深挖和压力追问回答。
```

Place it near the existing comparison and interview materials.

- [ ] **Step 3: Verify the combined diff preserves every previous line**

```powershell
git diff -- docs/README.md docs/resume/README.md
```

Expected: the new entries are additive; no pre-existing addition is removed.

- [ ] **Step 4: Leave the dirty index files unstaged**

Do not stage or commit `docs/README.md` or `docs/resume/README.md`. Report that they contain both protected prior changes and the new navigation entry.

---

### Task 5: Final Content Review and Verification

**Files:**
- Verify: `docs/resume/DeepResearch核心差异面试与学习手册.md`
- Verify: `docs/README.md`
- Verify: `docs/resume/README.md`

**Interfaces:**
- Consumes: all completed content.
- Produces: a reviewed, link-valid, interview-ready guide.

- [ ] **Step 1: Check required counts and headings**

```powershell
$doc='docs/resume/DeepResearch核心差异面试与学习手册.md'
rg -n '^## (30 秒回答|90 秒回答|5 分钟回答)$' $doc
(rg -c '^## 差异 [1-5]：' $doc)
(rg -c '^## 点名追问：' $doc)
rg -n '^## (学习训练|模拟面试|30 分评分表|面试前检查清单)$' $doc
```

Expected: three answer levels, five differences, three named comparisons, and all four training sections.

- [ ] **Step 2: Search for unsafe or unfinished wording**

```powershell
$doc='docs/resume/DeepResearch核心差异面试与学习手册.md'
$markers=@(('T'+'BD'),('T'+'ODO'),('['+'N'+']'),'一定优于','完全解决','保证 exactly-once','已生产验证')
Select-String -Path $doc -Pattern $markers
```

Expected: no unfinished marker or unsupported absolute claim.

- [ ] **Step 3: Validate every local Markdown link**

Resolve each non-HTTP link relative to the guide. Expected: every path exists; fragment-free file links open successfully.

- [ ] **Step 4: Review the answer chain for contradictions**

Confirm that 30-second, 90-second, 5-minute, five-difference, competitor, and pressure answers all preserve these boundaries:

- mature projects may be stronger in model quality, data, ecosystem, or product completeness;
- this project differentiates on runtime governance and evaluability;
- design ambition is not represented as measured implementation;
- answer quality superiority requires same-protocol evidence.

- [ ] **Step 5: Review readability aloud**

Read the 30-second and 90-second answers at a natural speaking pace. Shorten clauses that require rereading, remove stacked nouns, and ensure the answers fit their stated durations.

- [ ] **Step 6: Run final Git checks**

```powershell
git diff --check
git status --short
```

Expected: the guide is committed; the two index files remain intentionally unstaged alongside pre-existing user changes; no unrelated file is staged.

---

## Final Handoff

Report the new guide path, its recommended usage order, the commit created for the guide, the intentionally uncommitted index changes, and the core answer in one sentence so the user can immediately begin rehearsal.
