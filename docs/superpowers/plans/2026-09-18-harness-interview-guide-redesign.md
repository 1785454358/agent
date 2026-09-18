# Harness Interview Guide Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a concise, truthful, interview-ready Harness study path while preserving the existing detailed source-reference material.

**Architecture:** Add one self-contained rapid-review guide as the primary learning entry point, then align the resume bullets, reading index, and complete FAQ around the same vocabulary. Mature production patterns, verified project implementation, and future improvements remain explicitly separated.

**Tech Stack:** Markdown, PowerShell validation, Git

**Spec:** `docs/superpowers/specs/2026-09-18-harness-interview-guide-redesign.md`

## Global Constraints

- Do not modify Harness application code.
- Preserve existing detailed architecture, source-reading, and memory documents.
- Preserve unrelated uncommitted workspace changes.
- Resume bullets may claim only behavior supported by current source or tests.
- Never claim arbitrary external side effects are exactly-once.
- Mark production patterns not implemented in the project as evolution directions.
- Use the terms Harness, LangGraph, State, Runtime Context, Tool Gateway, Evidence, Memory, Checkpoint, and Ledger consistently.

---

### Task 1: Create the primary Harness rapid-review guide

**Files:**
- Create: `docs/resume/Harness面试速记手册.md`

**Interfaces:**
- Consumes: terminology and implementation facts from the approved design and existing resume study documents.
- Produces: the canonical concise definitions, ten core problems, twelve modules, request lifecycle, twenty interview questions, project pitches, and final cram checklist used by Tasks 2–4.

- [ ] **Step 1: Write the guide skeleton and navigation**

Create headings for the definition, core problems, modules, lifecycle, reliability and security, twenty questions, project pitches, mapping table, and cram checklist. Add links to the existing architecture and source-reading documents for deeper study.

- [ ] **Step 2: Write the conceptual core**

For each core problem and module, state the problem, responsibility, non-responsibility, and project status. Explicitly label mature patterns, current implementation, and evolution directions.

- [ ] **Step 3: Write the twenty interview answers**

Use the fixed answer model: short conclusion, 30–60 second answer, project example, follow-up, and claim boundary. Keep the primary spoken answer compact enough to deliver without reading.

- [ ] **Step 4: Add project pitches and cram checklist**

Add 10-second, 90-second, and 3-minute project descriptions plus a 30-minute review order and the claims that must not be made.

- [ ] **Step 5: Validate the guide structure**

Run:

```powershell
rg -n "^(#|##|###) " "docs/resume/Harness面试速记手册.md"
rg -n "成熟模式|项目实现|演进方向|exactly-once|Prompt Injection|评测" "docs/resume/Harness面试速记手册.md"
```

Expected: all required sections are present; the three truth labels and production topics are explicitly represented.

### Task 2: Rewrite the resume core version

**Files:**
- Modify: `docs/resume/多模式深度研究Agent简历项目材料.md`

**Interfaces:**
- Consumes: the five resume themes and terminology established by Task 1.
- Produces: one directly usable five-bullet resume version while retaining the detailed optional bullet library.

- [ ] **Step 1: Replace the six-bullet lead version with five focused bullets**

Use these themes in order: unified Harness, controlled Agent loop and tool governance, evidence and context, memory, persistence and recovery. Keep the technology stack and project description concise.

- [ ] **Step 2: Add usage and truth-boundary notes**

State that the lead version contains current implementation only. Separate optional verified bullets from evolution topics that must not be written as completed work.

- [ ] **Step 3: Validate length and assertions**

Run:

```powershell
rg -n "^[-*] \*\*" "docs/resume/多模式深度研究Agent简历项目材料.md"
rg -n "保证|完全避免|exactly-once|自动路由|多租户" "docs/resume/多模式深度研究Agent简历项目材料.md"
```

Expected: the lead section contains exactly five bullets; strong claims are absent or explicitly bounded.

### Task 3: Rebuild the reading entry point

**Files:**
- Modify: `docs/resume/多模式深度研究Agent面试与学习资料/00-阅读目录.md`

**Interfaces:**
- Consumes: the rapid-review guide from Task 1 and existing detailed documents.
- Produces: three explicit learning routes for urgent review, systematic study, and source verification.

- [ ] **Step 1: Add the rapid-review guide as the first entry**

Link to `../Harness面试速记手册.md` and explain when to use it.

- [ ] **Step 2: Define three reading routes**

Document the 30-minute interview route, the systematic architecture route, and the source-verification route. Keep the existing document links available.

- [ ] **Step 3: Check local Markdown links**

Run a PowerShell link scan that resolves every relative `.md` target from the containing document directory and reports missing targets.

Expected: no missing local Markdown targets.

### Task 4: Prioritize and align the complete FAQ

**Files:**
- Modify: `docs/resume/多模式深度研究Agent面试与学习资料/05-面试高频问题与答案.md`

**Interfaces:**
- Consumes: the canonical twenty questions and vocabulary from Task 1.
- Produces: a full reference FAQ with priority markers and no contradictory claims.

- [ ] **Step 1: Add priority definitions and answer method**

Define P0 as must-master, P1 as common follow-up, and P2 as source-detail reference. Link the rapid-review guide as the P0 entry point.

- [ ] **Step 2: Mark the existing questions by priority**

Prefix every numbered question with `[P0]`, `[P1]`, or `[P2]`. The twenty rapid-review topics must map to P0 or P1 questions in this file.

- [ ] **Step 3: Add missing production-grade questions**

Add concise questions covering Prompt Injection and untrusted tool output, human approval for high-risk actions, observability and trace identity, offline/online evaluation, model and prompt versioning, cancellation and backpressure, and safe concurrency.

- [ ] **Step 4: Check vocabulary and contradictions**

Search both the rapid guide and FAQ for obsolete terms, exactly-once claims, and statements that describe evolution work as completed behavior.

Expected: terminology matches, project boundaries are explicit, and no obsolete Topic-subgraph description is presented as current.

### Task 5: Perform cross-document verification

**Files:**
- Verify: `docs/resume/Harness面试速记手册.md`
- Verify: `docs/resume/多模式深度研究Agent简历项目材料.md`
- Verify: `docs/resume/多模式深度研究Agent面试与学习资料/00-阅读目录.md`
- Verify: `docs/resume/多模式深度研究Agent面试与学习资料/05-面试高频问题与答案.md`

**Interfaces:**
- Consumes: all outputs from Tasks 1–4.
- Produces: a consistent final interview-document set.

- [ ] **Step 1: Run Markdown and whitespace checks**

Run `git diff --check` on the four target files and scan all local Markdown links.

- [ ] **Step 2: Run assertion and terminology scans**

Search for `exactly-once`, `HarnessGraph`, obsolete current-use references to the Topic subgraph, unqualified multi-tenant claims, and unsupported performance percentages. Inspect every match.

- [ ] **Step 3: Compare the three spoken descriptions**

Confirm the resume description, 90-second pitch, and FAQ use the same project definition and the same boundaries between LangGraph and Harness.

- [ ] **Step 4: Review the final diff**

Use `git diff --` limited to the four target files. Confirm no unrelated working-tree content was rewritten.

- [ ] **Step 5: Commit the documentation set**

```powershell
git add -- "docs/resume/Harness面试速记手册.md" "docs/resume/多模式深度研究Agent简历项目材料.md" "docs/resume/多模式深度研究Agent面试与学习资料/00-阅读目录.md" "docs/resume/多模式深度研究Agent面试与学习资料/05-面试高频问题与答案.md"
git commit -m "docs: add harness interview preparation guide"
```
