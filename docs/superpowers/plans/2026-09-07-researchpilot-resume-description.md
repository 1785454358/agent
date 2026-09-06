# ResearchPilot Resume Description Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a truthful, compact Chinese resume project entry and a one-minute interview introduction for ResearchPilot.

**Architecture:** Derive every claim from the approved resume spec and current repository documentation. Write the resume entry around the three execution modes, Agent planning/execution, ReAct tools, Supervisor collaboration, and cost-control techniques; keep unmeasured performance improvements outside the current claims.

**Tech Stack:** Chinese technical resume writing, Markdown, repository documentation, human-writing revision checks.

**Spec:** `docs/superpowers/specs/2026-09-07-researchpilot-resume-description-design.md`

## Global Constraints

- The resume entry contains a two-line introduction, one technology-stack line, and three to five technical bullets.
- The first bullet explicitly identifies Basic as a Workflow mode.
- Current claims use only implemented and verified capabilities.
- Do not state a Token, latency, accuracy, or quality improvement percentage before a fixed benchmark exists.
- State the verified automated test count as 210.
- Keep internal details such as field names, quota counters, and fallback reason codes out of the resume body.
- Provide a separate one-minute interview introduction and a short list of likely follow-up questions.

---

### Task 1: Draft the Resume Project Entry

**Files:**
- Create: `docs/resume/researchpilot-project-experience.md`

**Interfaces:**
- Consumes: facts and wording boundaries in `docs/superpowers/specs/2026-09-07-researchpilot-resume-description-design.md`.
- Produces: a copy-ready section headed `ResearchPilot｜多模式深度研究 Agent｜个人项目`.

- [ ] **Step 1: Build the factual claim list**

Use these verified claims as the complete factual source:

```text
Basic is a fixed Workflow.
Deep is Plan-and-Execute with a ReAct Executor and feedback-based replanning.
Multi-Agent is a LangGraph Supervisor plus parallel ReAct Researchers.
Tools cover web search, page fetching, and historical memory retrieval.
BGE-M3 selects relevant original webpage passages for Writer input.
FastAPI and SSE expose execution and progress.
Parallel execution, local context filtering, caching, single-flight reuse,
terminal short-circuiting, and targeted follow-ups control avoidable work.
The current full automated suite has 210 passing tests.
```

- [ ] **Step 2: Write the copy-ready project block**

Create exactly these parts:

```markdown
## 可直接放入简历的版本

**ResearchPilot｜多模式深度研究 Agent｜个人项目**

[Two concise introduction lines]

**技术栈**  [One line]

- [Workflow and three-mode architecture]
- [Planning, execution feedback, and dynamic replanning]
- [ReAct tools, original webpage context, BGE-M3, and memory]
- [Supervisor, parallel Researchers, and targeted follow-up]
- [Performance/cost-control mechanisms plus 210 tests]
```

Each bullet starts with an implementation action and ends with the capability or engineering result. Keep each bullet within two visual lines in a normal resume editor.

- [ ] **Step 3: Run a factual boundary check**

Search the draft for unsupported claims:

```powershell
rg -n "提升[0-9]|降低[0-9]|生产级|超过|用户量|准确率|SOTA|显著" docs/resume/researchpilot-project-experience.md
```

Expected: no matches. Any match must be removed unless the spec explicitly supports it.

---

### Task 2: Add Interview Material and Revise the Chinese

**Files:**
- Modify: `docs/resume/researchpilot-project-experience.md`

**Interfaces:**
- Consumes: the copy-ready project block from Task 1.
- Produces: a one-minute spoken introduction, five likely interviewer questions, and concise answer points.

- [ ] **Step 1: Add the spoken introduction**

Add `## 一分钟面试介绍`. The introduction must naturally cover why the project exists, how the three modes differ, how Multi-Agent closes research gaps, and what the next evaluation milestone is. Do not read the resume bullets aloud in sequence.

- [ ] **Step 2: Add likely follow-up questions**

Add `## 面试追问准备` with concise answer points for exactly these questions:

```text
为什么同时保留 Workflow、Plan-and-Execute 和 Multi-Agent？
Supervisor 和普通 Planner 有什么区别？
如何避免 Researcher 重复搜索或偏离任务？
如何控制报告幻觉和引用错误？
为什么目前没有写 Token 降幅，下一步怎样评测？
```

- [ ] **Step 3: Apply the human-writing revision rules**

Read `human-writing/references/revision.md`, revise the draft, then run:

```powershell
python C:\Users\defaultuser0.DESKTOP-8HBNEFK\.agents\skills\human-writing\scripts\check_prose.py docs/resume/researchpilot-project-experience.md
```

Expected: no hard-rule failures. Resume-required punctuation inside technology names and URLs is exempt only where the checker permits it.

- [ ] **Step 4: Verify structure and claims**

Manually confirm:

```text
Introduction is two lines.
Technology stack is one line.
There are five technical bullets.
Basic is explicitly called Workflow.
No unmeasured percentage appears.
The test count is 210.
The interview introduction is about one minute when read aloud.
```

- [ ] **Step 5: Commit the writing artifact**

```powershell
git add -- docs/resume/researchpilot-project-experience.md
git diff --cached --check
git commit -m "docs: add ResearchPilot resume project entry"
```
