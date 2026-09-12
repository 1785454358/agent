# Harness Interview Guide Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the multi-mode deep-research Agent interview guide so that the project-defined Agent Harness is the narrative spine while LangGraph, research modes, tools, state, memory, recovery, and output remain accurately separated.

**Architecture:** Keep the existing single Markdown guide because it is one interview artifact, but rewrite it in two reviewable passes. The first pass establishes the project introduction and end-to-end Harness lifecycle; the second pass rewrites the deep-dive answers and performs mechanical terminology and prose checks.

**Tech Stack:** Markdown, PowerShell, ripgrep, Git

**Spec:** `docs/superpowers/specs/2026-09-11-harness-resume-interview-design.md`

## Global Constraints

- Agent Harness is a project-defined runtime governance layer, not a LangGraph official architecture, specification, or type.
- LangGraph is described as the state orchestration and durable-execution runtime used to implement the top-level `StateGraph` and research strategy subgraphs.
- Use “研究模式” for Workflow, Plan-and-Execute, and Multi-Agent; use “研究策略子图” for their LangGraph implementations.
- Use `ResearchMode`, `StrategyRegistry`, and `ResearchStrategyGraph` only when exact domain or code-facing names improve the explanation.
- Do not use Research Profile, Profile Registry, Profile 子图, `HarnessGraph`, “Agent Harness 主图”, or “LangGraph Agent Harness” as architecture terms in the delivered guide.
- Do not present “连续追问” or “多轮对话” as a project feature, interview topic, or opening selling point.
- Preserve short-term state, working memory, sliding-window context, structured compression, and long-term-memory lifecycle as technical Harness responsibilities.
- Default output is a concise answer; Report is selected only when the user explicitly requests a report.
- Preserve the verified MySQL, Redis, Evidence Store, retry ownership, Checkpoint, idempotency, and at-least-once boundaries from the existing guide.
- Do not modify, stage, or commit the paused Tool Gateway budget files under `backend/src/deeptrace/tools/budget.py` and `backend/tests/tools/`.

---

### Task 1: Rebuild the project introduction around the Agent Harness

**Files:**
- Modify: `docs/resume/researchpilot-harness-interview-guide.md:1-57`

**Interfaces:**
- Consumes: the terminology and narrative constraints in `docs/superpowers/specs/2026-09-11-harness-resume-interview-design.md`
- Produces: a coherent opening, 90-second answer, 3-minute answer, request lifecycle, and module-boundary table that later deep-dive answers can expand

- [ ] **Step 1: Record the current forbidden-term baseline**

Run:

```powershell
rg -n "Research Profile|Profile Registry|Profile 子图|HarnessGraph|Agent Harness 主图|LangGraph Agent Harness|连续追问|多轮对话" docs/resume/researchpilot-harness-interview-guide.md
```

Expected: matches appear in the opening, project introductions, lifecycle, module table, and later deep-dive sections. Save the output only for comparison; do not treat the existing wording as the target design.

- [ ] **Step 2: Rewrite the opening and both spoken introductions**

Edit the opening, “90 秒项目介绍”, and “3 分钟项目介绍” so both spoken answers follow this order:

```text
复杂开放问题需要检索、原文阅读和交叉验证
→ 项目基于 LangGraph 实现统一 Agent Harness
→ Harness 规定所有研究运行共享的状态与治理协议
→ 三种研究模式通过统一契约接入各自策略子图
→ Tool Gateway、Evidence、Memory、Checkpoint 与输出在同一生命周期内协作
→ 最后交代恢复语义和工程边界
```

The 90-second version should keep one concrete sentence for each link. The 3-minute version should expand the same chain with `ResearchOutcome`, State ownership, Tool Gateway ordering, Evidence references, Memory lifecycle, MySQL/Redis ownership, and at-least-once limits. Neither version may open with a list of technology names.

- [ ] **Step 3: Rewrite the request lifecycle**

Replace “一次请求怎样经过 Harness” with a lifecycle whose numbered steps use these owners and transitions:

```text
API creates run identity and validates ResearchMode
→ top-level StateGraph restores serializable state and normalizes the request
→ context assembly and intent routing decide whether research is needed
→ StrategyRegistry resolves one ResearchStrategyGraph
→ the strategy subgraph calls ModelGateway and Tool Gateway through Runtime Context
→ Evidence Store owns body content while State receives references and findings
→ response routing selects Answer, Brief, or explicit Report
→ Memory consolidation and Checkpoint close the run
```

Remove ordinary-follow-up, incremental-research, and mode-switch examples from this section. Keep `thread_id` only where it explains Checkpoint identity, Lease serialization, or memory scope.

- [ ] **Step 4: Rewrite the Harness module-boundary table**

Use these row names:

```text
顶层 StateGraph
StrategyRegistry
Runtime Context
State
ModelGateway
Tool Gateway
Evidence Store
Memory 子系统
Checkpointer
Observability
```

The table must make the Harness visible as the protocol formed by these cooperating boundaries, rather than as one class or graph. Replace mode permissions and observability labels with `ResearchMode` or “研究模式”. Add ModelGateway as the owner of model-call retry and telemetry policy.

- [ ] **Step 5: Review the rewritten opening as spoken material**

Read both versions aloud or use a timer. Expected results:

```text
90 秒版本约 250 至 400 个汉字
3 分钟版本约 650 至 1000 个汉字
第一次出现 Agent Harness 时立即说明它是项目实现的运行治理层
第一次出现 LangGraph 时说明它负责状态图编排与持久化执行
每段都能自然引出下一段，没有连续的模块名堆叠
```

- [ ] **Step 6: Commit the narrative and lifecycle rewrite**

Run:

```powershell
git add -- docs/resume/researchpilot-harness-interview-guide.md
git diff --cached --check
git commit -m "docs: rebuild harness interview narrative"
```

Expected: only the interview guide is committed. The paused budget files remain untracked.

### Task 2: Align every deep-dive answer with the Harness narrative

**Files:**
- Modify: `docs/resume/researchpilot-harness-interview-guide.md:59-187`

**Interfaces:**
- Consumes: the ownership model and terminology established by Task 1
- Produces: an interview guide whose questions expand one consistent Harness design and contain no legacy architecture terms

- [ ] **Step 1: Rewrite the Harness and LangGraph explanation**

Replace the first deep-dive group with separate answers to these questions:

```text
这个项目里的 Agent Harness 指什么
Harness 和 LangGraph 分别负责什么
为什么三种研究模式都实现为 LangGraph 策略子图
三种策略子图怎样共享能力并隔离私有状态
```

The first answer must define Harness through observable responsibilities. The second must assign graph execution, State transitions, subgraphs, conditional edges, Checkpoint boundaries, and interrupts to LangGraph, while assigning shared runtime policy and lifecycle governance to the project Harness. The remaining answers must use `ResearchInput` and `ResearchOutcome` as the common boundary.

- [ ] **Step 2: Rewrite response, tool, evidence, and memory answers**

Rename the research/output separation question to “研究模式和响应模式为什么分开”. Explain that research modes obtain evidence while Answer, Brief, and Report control presentation. Preserve the explicit Report trigger.

In the Tool Gateway answer, replace “Profile Allowlist” with a ResearchMode-aware allowlist and preserve this execution order:

```text
registry resolution
→ mode allowlist
→ argument validation
→ security policy
→ idempotency lookup
→ budget reservation
→ cache and singleflight
→ provider execution
→ evidence persistence
→ budget commit or release
→ event recording
```

Keep the Evidence ownership answer, working-memory/State explanation, sliding-window compression, and all six long-term-memory lifecycle decisions. Remove sentences whose only purpose is to advertise conversational follow-up.

- [ ] **Step 3: Rewrite reliability and research-mode comparison answers**

Preserve the three crash windows and explicitly distinguish Checkpoint state recovery from Tool Execution Ledger result reuse. Keep the community MySQL Checkpointer limitation, MySQL/Redis ownership, and at-least-once semantics.

Rename all comparison and selection headings and tables to “研究模式”. The final comparison must say that Workflow, Plan-and-Execute, and Multi-Agent use the same model, providers, budgets, and Evidence rules so quality, cost, and latency differences can be attributed to strategy behavior.

- [ ] **Step 4: Run the forbidden-term and required-term checks**

Run:

```powershell
$forbidden = rg -n "Research Profile|Profile Registry|Profile 子图|HarnessGraph|Agent Harness 主图|LangGraph Agent Harness|连续追问|多轮对话" docs/resume/researchpilot-harness-interview-guide.md
if ($LASTEXITCODE -eq 0) { $forbidden; throw 'Forbidden interview terminology remains' }
$required = rg -n "Agent Harness|LangGraph|研究模式|研究策略子图|StrategyRegistry|Tool Gateway|Evidence Store|Memory|Checkpointer|Report" docs/resume/researchpilot-harness-interview-guide.md
if ($LASTEXITCODE -ne 0) { throw 'Required Harness narrative terms are missing' }
$required
```

Expected: the forbidden search returns no matches; the required search lists all major Harness responsibilities.

- [ ] **Step 5: Run Markdown and prose checks**

Run:

```powershell
git diff --check -- docs/resume/researchpilot-harness-interview-guide.md
python "C:/Users/defaultuser0.DESKTOP-8HBNEFK/.agents/skills/human-writing/scripts/check_prose.py" docs/resume/researchpilot-harness-interview-guide.md
```

Expected: `git diff --check` reports no whitespace errors and the prose checker reports no prohibited Chinese prose patterns. If the checker flags code literals or URLs, inspect each match and revise prose around them without changing exact code identifiers.

- [ ] **Step 6: Perform a factual consistency review**

Compare the final guide with `docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md` and verify all of the following:

```text
Writer belongs only to response graphs
Tool Gateway owns tool calls and ModelGateway owns model calls
Provider SDK retry is zero and LangGraph Node RetryPolicy is the sole transient retry layer
Evidence Store uniquely owns bounded body records
State and long-term memory store Evidence references
community MySQL package provides only the claimed Checkpointer behavior
project MySQL Memory Store owns long-term memory
Redis is not an authoritative state source
exactly-once is not claimed
```

Expected: every statement in the guide matches the final design; unsupported performance figures or completed-feature claims are absent.

- [ ] **Step 7: Commit the deep-dive rewrite**

Run:

```powershell
git add -- docs/resume/researchpilot-harness-interview-guide.md
git diff --cached --check
git commit -m "docs: align harness interview deep dives"
git status --short
```

Expected: the interview-guide changes are committed, and only the previously paused budget files remain untracked.
