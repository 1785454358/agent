# Harness Resume and Interview Materials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Harness-centered resume entry, selectable detail bullets, and an interview guide for the completed form of the multi-mode deep research Agent.

**Architecture:** Keep the resume concise and selection-oriented while moving explanations into a separate interview guide. Use one approved terminology table across both files so Profile names, MySQL persistence, memory lifecycle, Tool Gateway, output routing, and recovery claims remain consistent.

**Tech Stack:** Markdown, Chinese technical writing, Git, repository design documents.

**Spec:** `docs/superpowers/specs/2026-09-11-harness-resume-interview-design.md`

## Global Constraints

- The public project title is `多模式深度研究 Agent`.
- The final Profile names are `Workflow`, `Plan-and-Execute`, and `Multi-Agent`.
- Agent orchestration is uniformly implemented with LangGraph.
- Default output is a concise answer; a report is generated only on explicit request.
- Short-term memory uses a sliding window plus structured dynamic compression.
- Long-term memory explains when to store, what to store, organization, recall, update, and forgetting.
- MySQL persistence uses the community `langgraph-checkpoint-mysql[asyncmy]` adapter and must not be called official built-in MySQL support.
- Redis Streams transports work and wakeups; MySQL remains authoritative.
- Do not invent quantitative production results.
- Preserve the currently paused uncommitted Task 3 files without editing or staging them.

---

### Task 1: Rewrite the resume entry and selectable bullet library

**Files:**

- Modify: `docs/resume/researchpilot-project-experience.md`

**Interfaces:**

- Consumes: the terminology and factual boundaries in the approved spec.
- Produces: a copy-ready five-bullet resume version and a categorized pool of optional replacement bullets.

- [ ] **Step 1: Replace the old project title and description**

Use the exact title `多模式深度研究 Agent`, retain `独立开发`, and retain the user's date range. The description must introduce the unified Harness and three Profiles within two resume lines.

- [ ] **Step 2: Write the five-bullet core version**

Cover Agent Harness, three Profiles, Tool Gateway and Evidence, memory and context, and persistence and recovery. Each bullet must contain an implemented mechanism and the engineering problem it addresses.

- [ ] **Step 3: Write the optional bullet library**

Provide independently selectable bullets for Harness lifecycle, Profile registry and subgraphs, Tool middleware, Evidence and citations, sliding-window memory, dynamic compression, long-term memory lifecycle, multi-turn routing, MySQL checkpoint recovery, Redis delivery, budget and idempotency, and evaluation. Memory must occupy at least three separate bullets.

- [ ] **Step 4: Remove stale claims**

Run:

```powershell
rg -n "Basic|Deep（|为什么没有做对话式|默认.*报告|ResearchPilot" docs/resume/researchpilot-project-experience.md
```

Expected: no matches in the rewritten public material.

- [ ] **Step 5: Check the required final terminology**

Run:

```powershell
rg -n "多模式深度研究 Agent|Agent Harness|Workflow|Plan-and-Execute|Multi-Agent|滑动窗口|动态压缩|长期记忆|MySQL|Redis" docs/resume/researchpilot-project-experience.md
```

Expected: every required topic has at least one match.

- [ ] **Step 6: Commit the resume material only**

```powershell
git add -- docs/resume/researchpilot-project-experience.md
git commit -m "docs: rewrite harness resume material"
```

### Task 2: Create the Harness interview guide

**Files:**

- Create: `docs/resume/researchpilot-harness-interview-guide.md`

**Interfaces:**

- Consumes: every claim in the Task 1 core and optional bullets.
- Produces: spoken project introductions, one request lifecycle, technical deep dives, trade-offs, and likely follow-ups.

- [ ] **Step 1: Write spoken introductions**

Add a 90-second version and a 3-minute version. Both begin with the user problem and explain why the Harness is the project's organizing abstraction.

- [ ] **Step 2: Explain one complete request lifecycle**

Cover request normalization, intent and Profile routing, short-term context, optional long-term recall, Profile subgraph execution, Tool Gateway, Evidence ingestion, response routing, memory consolidation, checkpointing, and events.

- [ ] **Step 3: Explain the Harness modules**

For HarnessGraph, Profile Registry, Runtime Context, State, Tool Gateway, Evidence Store, Memory subsystem, Checkpointer, and observability, state responsibility, inputs and outputs, and failure boundary.

- [ ] **Step 4: Add deep-dive answers**

Include directly speakable answers for Harness versus an ordinary Agent wrapper, all-LangGraph orchestration, shared capabilities with isolated Profile state, Tool Gateway ordering, Evidence references in State, sliding window plus dynamic compression, the six-part long-term memory lifecycle, checkpoint and idempotency recovery, MySQL Checkpointer selection and limits, Redis and MySQL responsibility boundaries, and Profile quality/cost/latency evaluation. The MySQL answer must acknowledge that the Checkpointer is a community implementation of `BaseCheckpointSaver`, then explain compatibility and recovery verification.

- [ ] **Step 5: Add comparison and trade-off answers**

Explain why three Profiles remain visible, when each is selected, why `auto` is deferred, why composite research is a graph instead of a tool, why Evidence bodies stay out of graph State, and why delivery is described as at-least-once rather than exactly-once.

- [ ] **Step 6: Add mock interview protocol**

End with the first interviewer question and instructions to answer one question per round. Do not pre-answer an entire interview transcript in the guide.

- [ ] **Step 7: Verify claim coverage**

Run:

```powershell
rg -n "HarnessGraph|Profile Registry|Runtime Context|Tool Gateway|Evidence Store|滑动窗口|动态压缩|何时存|何时召回|如何更新|如何遗忘|BaseCheckpointSaver|at-least-once" docs/resume/researchpilot-harness-interview-guide.md
```

Expected: every pattern appears in an explanatory section.

- [ ] **Step 8: Commit the interview guide only**

```powershell
git add -- docs/resume/researchpilot-harness-interview-guide.md
git commit -m "docs: add harness interview guide"
```

### Task 3: Cross-document editorial and factual verification

**Files:**

- Modify: `docs/resume/researchpilot-project-experience.md`
- Modify: `docs/resume/researchpilot-harness-interview-guide.md`

**Interfaces:**

- Consumes: completed Task 1 and Task 2 documents.
- Produces: consistent, readable final materials ready for selection and mock interviewing.

- [ ] **Step 1: Verify terminology consistency**

Run:

```powershell
rg -n "PostgreSQL|Basic|Deep（|exactly-once|官方.*MySQL|MySQL.*官方" docs/resume/researchpilot-project-experience.md docs/resume/researchpilot-harness-interview-guide.md
```

Expected: no misleading final-architecture matches. `exactly-once` may appear only while explicitly rejecting that guarantee.

- [ ] **Step 2: Verify every resume claim is explainable**

Check these exact mappings: Agent Harness to HarnessGraph and lifecycle, three Profiles to Profile comparison, Tool Gateway and Evidence to tool pipeline and citation control, memory and context to short-term and long-term memory, persistence and recovery to MySQL Checkpointer and Redis delivery. Remove any resume claim with no corresponding mechanism or failure boundary.

- [ ] **Step 3: Apply the Chinese revision checklist**

Read `C:/Users/defaultuser0.DESKTOP-8HBNEFK/.agents/skills/human-writing/references/revision.md`, then revise repetition, inflated claims, awkward spoken sentences, forbidden rhetorical patterns, and unsupported facts.

- [ ] **Step 4: Run the prose checker**

Run:

```powershell
python C:/Users/defaultuser0.DESKTOP-8HBNEFK/.agents/skills/human-writing/scripts/check_prose.py docs/resume/researchpilot-project-experience.md
python C:/Users/defaultuser0.DESKTOP-8HBNEFK/.agents/skills/human-writing/scripts/check_prose.py docs/resume/researchpilot-harness-interview-guide.md
```

Expected: no hard-rule violations. Technical URLs, code identifiers, and resume field labels are reviewed in their permitted context.

- [ ] **Step 5: Confirm paused implementation files remain separate**

Run:

```powershell
git status --short
```

Expected: the Task 3 budget files remain uncommitted and are never included in documentation commits.

- [ ] **Step 6: Commit editorial corrections if needed**

```powershell
git add -- docs/resume/researchpilot-project-experience.md docs/resume/researchpilot-harness-interview-guide.md
git commit -m "docs: polish harness interview materials"
```
