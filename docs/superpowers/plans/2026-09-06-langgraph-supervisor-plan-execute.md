# LangGraph Supervisor Plan-and-Execute Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-written Multi-Agent coordination loop with a real LangGraph Plan → parallel Execute → Replan loop that preserves task state, follows up material gaps, and cannot accept an early insufficient finish while capacity remains.

**Architecture:** `multi_agent` gets a persistent typed task ledger and a four-node LangGraph: `plan`, `execute`, `replan`, and `writer`. Supervisor plans and patches the ledger, the execute node runs isolated ReAct Researchers concurrently, deterministic graph invariants validate termination, and the existing Writer receives only actually read BGE-selected source text.

**Tech Stack:** Python 3.12, LangGraph `StateGraph`, asyncio, Pydantic v2, LangChain messages/tool calls, existing Researcher/resources/quota/Writer, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-06-langgraph-supervisor-plan-execute-design.md`

## Global Constraints

- Modify only the `multi_agent` strategy and optional shared Writer date arguments; do not change Basic or Deep execution semantics.
- The graph topology must be `START → plan → execute → replan`, with `replan → execute` or `replan → writer`, and `writer → END`.
- Keep defaults at 6 total Researchers, 3 per batch, concurrency 3, 3 Supervisor decisions, 3 Researcher decisions, 30 total network attempts, and 10 attempts per Researcher.
- Time, Token, and estimated cost remain observations, never whole-run stop budgets.
- Keep two Researcher tool decisions plus one finish-only decision and at most one model-selected research tool per decision.
- Writer facts must come only from actually read BGE-selected original text; do not add ResearchNote, Claim, Evidence, Verifier, or per-page LLM summaries.
- Preserve API/CLI mode `multi_agent`, `AgentResult`, SSE, numbered headings, first-use numeric citations, and reference URLs at the end.
- Do not run a paid Provider/Tavily benchmark without explicit user authorization.
- The working tree contains the user's earlier uncommitted restructure. Stage exact reviewed paths only; never stage reports, logs, `.env`, `1.txt`, or unrelated user files.

---

### Task 1: Add the persistent task ledger and pure plan-state selectors

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/models.py`
- Create: `backend/src/deeptrace/multi_agent/state.py`
- Create: `backend/tests/multi_agent/test_state.py`

**Interfaces:**
- Consumes: existing `ResearchAssignment` and `ResearcherResult`.
- Produces: `PlannedTask`, `MultiAgentGraphState`, `ready_task_ids(tasks)`, `open_leaf_tasks(tasks)`, `leaf_gaps(tasks)`, and `compact_task_history(tasks)`.
- `tasks` is `dict[str, PlannedTask]`; a key must equal `task.assignment.id`.

- [ ] **Step 1: Write failing ledger invariant and selector tests**

Create `test_state.py` with real models and literal expectations:

```python
from deeptrace.multi_agent.models import PlannedTask, ResearchAssignment, ResearcherResult
from deeptrace.multi_agent.state import (
    compact_task_history,
    leaf_gaps,
    open_leaf_tasks,
    ready_task_ids,
)


def assignment(task_id, *, parents=()):
    return ResearchAssignment(
        id=task_id,
        objective=f"研究 {task_id}",
        required_outputs=[f"{task_id} 检查项"],
        parent_ids=list(parents),
    )


def result(task_id, status, gaps=()):
    return ResearcherResult(
        task_id=task_id,
        status=status,
        summary=f"{task_id} 结果",
        source_urls=[] if status == "blocked" else [f"https://example.com/{task_id}"],
        gaps=list(gaps),
        stop_reason="completed" if status == "completed" else "round_limit",
    )


def test_ready_tasks_require_executed_parents():
    tasks = {
        "r1": PlannedTask(assignment=assignment("r1")),
        "r2": PlannedTask(assignment=assignment("r2", parents=("r1",))),
    }
    assert ready_task_ids(tasks) == ["r1"]
    tasks["r1"] = PlannedTask(
        assignment=assignment("r1"), status="partial",
        result=result("r1", "partial", ["发布日期未确认"]),
    )
    assert ready_task_ids(tasks) == ["r2"]


def test_followup_supersedes_parent_gaps_for_final_status():
    tasks = {
        "r1": PlannedTask(
            assignment=assignment("r1"), status="partial",
            result=result("r1", "partial", ["旧缺口"]),
        ),
        "r2": PlannedTask(
            assignment=assignment("r2", parents=("r1",)), status="completed",
            result=result("r2", "completed"),
        ),
    }
    assert open_leaf_tasks(tasks) == []
    assert leaf_gaps(tasks) == []


def test_compact_history_omits_urls_and_page_text():
    tasks = {
        "r1": PlannedTask(
            assignment=assignment("r1"), status="partial",
            result=result("r1", "partial", ["仍缺官方文件"]),
        )
    }
    history = compact_task_history(tasks)
    assert history[0]["source_count"] == 1
    assert "source_urls" not in history[0]
    assert "content" not in history[0]
```

- [ ] **Step 2: Run the state tests and verify RED**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_state.py -q
```

Expected: collection fails because `PlannedTask` and `multi_agent.state` do not exist.

- [ ] **Step 3: Add `PlannedTask` with strict status/result consistency**

In `models.py` add:

```python
class PlannedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment: ResearchAssignment
    status: Literal["pending", "running", "completed", "partial", "blocked"] = "pending"
    result: ResearcherResult | None = None

    @model_validator(mode="after")
    def validate_result(self) -> PlannedTask:
        terminal = self.status in {"completed", "partial", "blocked"}
        if terminal != (self.result is not None):
            raise ValueError("terminal task status and result must agree")
        if self.result is not None and self.result.task_id != self.assignment.id:
            raise ValueError("task result ID must match assignment ID")
        return self
```

- [ ] **Step 4: Implement typed graph state and pure selectors**

Create `state.py` with:

```python
class MultiAgentGraphState(TypedDict):
    question: str
    current_date: str
    timezone: str
    tasks: dict[str, PlannedTask]
    ready_task_ids: list[str]
    next_task_number: int
    supervisor_iteration: int
    supervisor_circuit_open: bool
    first_batch: bool
    final_sufficient: bool
    final_gaps: list[str]
    termination_reason: str
    research_context: str
    final_sources: list[str]
    final_answer: str
    events: list[RunEvent]
    role_usage: UsageBreakdown
    stage_seconds: dict[str, float]
    step_count: int


def ready_task_ids(tasks: Mapping[str, PlannedTask]) -> list[str]:
    executed = {task_id for task_id, task in tasks.items() if task.result is not None}
    return [
        task_id for task_id, task in tasks.items()
        if task.status == "pending" and set(task.assignment.parent_ids) <= executed
    ]


def open_leaf_tasks(tasks: Mapping[str, PlannedTask]) -> list[PlannedTask]:
    parent_ids = {
        parent
        for task in tasks.values()
        if task.result is not None
        for parent in task.assignment.parent_ids
    }
    return [
        task for task_id, task in tasks.items()
        if task_id not in parent_ids
        and task.status in {"partial", "blocked"}
        and task.result is not None
        and task.result.gaps
    ]


def leaf_gaps(tasks: Mapping[str, PlannedTask]) -> list[str]:
    return list(dict.fromkeys(
        gap for task in open_leaf_tasks(tasks) for gap in task.result.gaps
    ))[:6]
```

`compact_task_history` must return only assignment ID/objective/required outputs/excluded scope/source guidance/parents plus result status/summary/gaps/source count. It must preserve insertion order and never include URLs or page text.

- [ ] **Step 5: Run focused tests and commit the ledger**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_state.py tests/multi_agent/test_models.py -q
uvx ruff check src/deeptrace/multi_agent/models.py src/deeptrace/multi_agent/state.py tests/multi_agent/test_state.py
git add -- backend/src/deeptrace/multi_agent/models.py backend/src/deeptrace/multi_agent/state.py backend/tests/multi_agent/test_state.py
git diff --cached --name-only
git commit -m "feat: add multi-agent plan ledger"
```

Expected: tests and Ruff pass; staged paths contain only the three listed files.

### Task 2: Separate Supervisor planning/replanning and add deterministic gap fallback

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/models.py`
- Modify: `backend/src/deeptrace/multi_agent/prompts.py`
- Modify: `backend/src/deeptrace/multi_agent/supervisor.py`
- Modify: `backend/tests/multi_agent/test_supervisor.py`

**Interfaces:**
- Consumes: compact task history from Task 1 and existing `SupervisorDecision`.
- Produces: `SupervisorOutcome(decision, circuit_open, fallback_reason)` and `build_gap_followups(history, max_assignments) -> list[AssignmentDraft]`.
- Produces: `Supervisor.plan(...) -> SupervisorOutcome` and `Supervisor.replan(...) -> SupervisorOutcome`.

- [ ] **Step 1: Write a failing timeout-to-followup regression for run `db2f3ea92e6b`**

Add a model that sleeps past a 0.01-second call timeout. Pass three partial compact-history items and assert:

```python
outcome = await supervisor.replan(
    "2025 AI 热点",
    history,
    current_date="2026-09-06",
    timezone="Asia/Shanghai",
    remaining_slots=3,
    max_assignments=3,
    circuit_open=False,
)
assert model.calls == 1
assert outcome.circuit_open
assert outcome.fallback_reason == "provider_timeout"
assert outcome.decision.action == "dispatch"
assert [item.parent_ids for item in outcome.decision.assignments] == [
    ["r1"], ["r2"], ["r3"]
]
```

- [ ] **Step 2: Write failing deterministic fallback grouping tests**

Use a parent with five concrete gaps and assert the follow-up has no more than three required outputs, every original gap occurs in one group, inherited source guidance is de-duplicated, and `excluded_scope` contains `不重复已确认内容`.

Also test `circuit_open=True` with a model that raises if called; `replan` must return deterministic follow-ups without calling the model.

- [ ] **Step 3: Run Supervisor tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_supervisor.py -q
```

Expected: failures show two timeout attempts and a finish-only fallback.

- [ ] **Step 4: Add typed Supervisor outcome and gap grouping**

Add to `models.py`:

```python
class SupervisorOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: SupervisorDecision
    circuit_open: bool = False
    fallback_reason: str | None = None
```

In `supervisor.py`, implement a stable grouping helper:

```python
def _group_gaps(gaps: list[str], groups: int = 3) -> list[str]:
    clean = list(dict.fromkeys(gap.strip() for gap in gaps if gap.strip()))
    buckets = [[] for _ in range(min(groups, len(clean)))]
    for index, gap in enumerate(clean):
        buckets[index % len(buckets)].append(gap)
    return ["；".join(bucket)[:1000] for bucket in buckets]
```

`build_gap_followups` creates at most one assignment per open leaf parent, with grouped gaps, `parent_ids=[task_id]`, inherited bounded exclusions/source guidance, and no generated task IDs.

- [ ] **Step 5: Implement `plan` and `replan` with timeout circuit breaking**

Both methods call a shared private validator, but use distinct prompts. Rules:

```python
if circuit_open:
    return deterministic_outcome(history, max_assignments, "circuit_open")

try:
    response = await runtime.invoke(bound, messages, "supervisor")
except TimeoutError:
    return deterministic_outcome(history, max_assignments, "provider_timeout", circuit_open=True)
```

Do not retry `provider_timeout`. Keep one repair for missing/multiple/invalid tool structures. A failed initial plan with empty history returns insufficient finish; a failed replan with actionable history returns deterministic dispatch.

- [ ] **Step 6: Pass current date and a compact plan patch to prompts**

`supervisor_messages` receives `phase`, `current_date`, `timezone`, and compact history. Its system instruction must say the application date is authoritative, preserve existing tasks, add only gap-targeted tasks on replan, and never claim a year before `current_date[:4]` has not occurred.

- [ ] **Step 7: Run focused tests and commit Supervisor behavior**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_supervisor.py tests/multi_agent/test_models.py -q
uvx ruff check src/deeptrace/multi_agent/models.py src/deeptrace/multi_agent/prompts.py src/deeptrace/multi_agent/supervisor.py tests/multi_agent/test_supervisor.py
git add -- backend/src/deeptrace/multi_agent/models.py backend/src/deeptrace/multi_agent/prompts.py backend/src/deeptrace/multi_agent/supervisor.py backend/tests/multi_agent/test_supervisor.py
git diff --cached --name-only
git commit -m "fix: make supervisor replanning recoverable"
```

### Task 3: Move concurrent Researcher execution into a graph node service

**Files:**
- Create: `backend/src/deeptrace/multi_agent/nodes.py`
- Create: `backend/tests/multi_agent/test_nodes.py`
- Modify: `backend/src/deeptrace/multi_agent/researcher.py`
- Modify: `backend/src/deeptrace/multi_agent/prompts.py`

**Interfaces:**
- Consumes: `MultiAgentGraphState`, `PlannedTask`, `Researcher`, resources/quota, and `SupervisorOutcome`.
- Produces: `MultiAgentWorkflowNodes.plan_node`, `.execute_node`, `.replan_node`, `.writer_node` async methods returning partial state dictionaries.
- The node service owns process-local dependencies; serializable coordination data remains in graph state.

- [ ] **Step 1: Write failing plan-node ledger tests**

Use a fake Supervisor returning two assignment drafts. Assert `plan_node` adds r1/r2 as pending, sets `next_task_number=3`, increments `supervisor_iteration`, and returns `ready_task_ids == ["r1", "r2"]`. A failed initial plan must set `termination_reason="planning_failed"` and no ready tasks.

- [ ] **Step 2: Write a failing barrier-based execute-node test**

With three pending tasks and concurrency 2, use `asyncio.Event` barriers and assert:

```python
update = await nodes.execute_node(state)
assert max_active == 2
assert set(update["tasks"]) == {"r1", "r2", "r3"}
assert all(task.result is not None for task in update["tasks"].values())
assert [e.event_type for e in runtime.events].count("researcher.queued") == 3
assert [e.event_type for e in runtime.events].count("researcher.completed") == 3
```

Include a failing Researcher and verify the other two complete and every lease is released.

- [ ] **Step 3: Run node tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_nodes.py -q
```

Expected: collection fails because `MultiAgentWorkflowNodes` does not exist.

- [ ] **Step 4: Implement node dependency injection and telemetry snapshots**

The constructor accepts `runtime`, `supervisor`, `researcher_factory`, `resources`, `writer`, and settings. Add:

```python
def _telemetry(self) -> dict:
    return {
        "events": list(self.runtime.events),
        "role_usage": self.runtime.role_usage.model_copy(deep=True),
        "stage_seconds": dict(self.runtime.stage_seconds),
        "step_count": self.runtime.steps,
    }
```

Nodes return complete replacement snapshots for telemetry because only one top-level graph node runs per superstep.

- [ ] **Step 5: Move the existing batch logic into `execute_node`**

Copy behavior, not the enclosing `for` loop: allocate initial/follow-up leases, emit queued before the semaphore, emit started inside it, isolate task failures, release every lease in `finally`, gather all batch results, and replace each pending `PlannedTask` with a terminal record.

Set `ready_task_ids=[]` after the batch. Do not call Supervisor or Writer inside execute.

- [ ] **Step 6: Make Researcher prompts date-aware without changing tool limits**

Add optional `current_date` and `timezone` constructor fields to `Researcher`, pass them into `researcher_messages`, and include this literal input in the human message:

```python
{
    "application_current_date": current_date,
    "application_timezone": timezone,
    "question": question,
    "assignment": assignment.model_dump(),
}
```

Keep existing tool binding, payload caps, and finish-only last decision unchanged.

- [ ] **Step 7: Run execution and Researcher regressions, then commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_nodes.py tests/multi_agent/test_researcher.py tests/multi_agent/test_tools.py tests/multi_agent/test_resources.py -q
uvx ruff check src/deeptrace/multi_agent/nodes.py src/deeptrace/multi_agent/researcher.py src/deeptrace/multi_agent/prompts.py tests/multi_agent/test_nodes.py
git add -- backend/src/deeptrace/multi_agent/nodes.py backend/src/deeptrace/multi_agent/researcher.py backend/src/deeptrace/multi_agent/prompts.py backend/tests/multi_agent/test_nodes.py
git diff --cached --name-only
git commit -m "feat: execute researcher batches as graph nodes"
```

### Task 4: Enforce replanning and termination invariants in the node layer

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/nodes.py`
- Modify: `backend/src/deeptrace/multi_agent/state.py`
- Modify: `backend/tests/multi_agent/test_nodes.py`

**Interfaces:**
- Consumes: terminal task ledger after execute, Supervisor replan outcome, quota remaining, and configured loop/researcher limits.
- Produces: `route_after_plan(state) -> Literal["execute", "writer"]`, `route_after_replan(state) -> Literal["execute", "writer"]`, and a replan update that cannot prematurely finish.

- [ ] **Step 1: Write the failing `f6f6b84368bb` early-finish regression**

Construct three partial leaf tasks, total task count 3, `quota.remaining=14`, and a fake Supervisor that returns:

```python
SupervisorOutcome(
    decision=SupervisorDecision(
        action="finish",
        rationale="2025 has not occurred yet",
        sufficient=False,
        gaps=["2025 has not occurred yet"],
    )
)
```

Assert:

```python
update = await nodes.replan_node(state)
assert update["termination_reason"] == ""
assert update["ready_task_ids"] == ["r4", "r5", "r6"]
assert all(update["tasks"][task_id].status == "pending" for task_id in update["ready_task_ids"])
assert any(e.event_type == "plan.finish_rejected" for e in runtime.events)
```

- [ ] **Step 2: Write failing final leaf-gap and hard-limit tests**

Cases:

- completed r4 child suppresses partial r1 parent gap;
- partial r5 child replaces r2 parent gap with its own new gap;
- six total Researchers prevents adding more tasks and routes to Writer as partial;
- fewer than two remaining network attempts prevents dispatch;
- `sufficient=True` with no pending/open leaf tasks routes to Writer as completed;
- repeated follow-up batch with no new source URLs terminates as `stagnant` partial.

- [ ] **Step 3: Run the exact regressions and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_nodes.py -k "finish_rejected or leaf or limit or stagnant" -q
```

Expected: the current node accepts insufficient finish or lacks the routing functions.

- [ ] **Step 4: Implement capacity and progress predicates**

Add pure helpers in `state.py`:

```python
def can_follow_up(state, *, quota_remaining: int, max_researchers: int) -> bool:
    return (
        bool(open_leaf_tasks(state["tasks"]))
        and len(state["tasks"]) < max_researchers
        and quota_remaining >= 2
        and state["supervisor_iteration"] < state["max_supervisor_iterations"]
    )


def source_urls(tasks) -> set[str]:
    return {
        url for task in tasks.values()
        if task.result is not None for url in task.result.source_urls
    }
```

Add `max_supervisor_iterations` and `sources_before_batch` to graph state so the router uses explicit state rather than hidden globals.

- [ ] **Step 5: Reject premature insufficient finish and add plan patches**

In `replan_node`:

```python
if decision.action == "finish" and not decision.sufficient and capacity:
    runtime.emit(
        "plan.finish_rejected",
        "主管建议结束，但仍有关键缺口和可用额度，转为定向补查",
        reason_code="incomplete_with_capacity",
    )
    drafts = build_gap_followups(compact_history, max_assignments)
else:
    drafts = decision.assignments if decision.action == "dispatch" else []
```

Add stable IDs to drafts, keep all existing tasks, and set only new task IDs ready. If Supervisor dispatches nothing useful, use the same deterministic drafts. If hard limits or stagnation apply, set `final_gaps=leaf_gaps(tasks)` and a precise termination reason.

- [ ] **Step 6: Implement deterministic routing functions**

```python
def route_after_plan(state):
    return "execute" if state["ready_task_ids"] else "writer"


def route_after_replan(state):
    return "execute" if state["ready_task_ids"] and not state["termination_reason"] else "writer"
```

The route never consults free-form Supervisor rationale.

- [ ] **Step 7: Run node/state tests and commit the control invariants**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_state.py tests/multi_agent/test_nodes.py -q
uvx ruff check src/deeptrace/multi_agent/state.py src/deeptrace/multi_agent/nodes.py tests/multi_agent/test_state.py tests/multi_agent/test_nodes.py
git add -- backend/src/deeptrace/multi_agent/state.py backend/src/deeptrace/multi_agent/nodes.py backend/tests/multi_agent/test_state.py backend/tests/multi_agent/test_nodes.py
git diff --cached --name-only
git commit -m "fix: enforce multi-agent replan invariants"
```

### Task 5: Compile the LangGraph and replace the hand-written agent loop

**Files:**
- Create: `backend/src/deeptrace/multi_agent/graph.py`
- Modify: `backend/src/deeptrace/multi_agent/agent.py`
- Modify: `backend/src/deeptrace/multi_agent/service.py`
- Modify: `backend/src/deeptrace/prompts/writer.py`
- Modify: `backend/src/deeptrace/writer/agent.py`
- Create: `backend/tests/multi_agent/test_graph.py`
- Modify: `backend/tests/multi_agent/test_agent.py`
- Modify: relevant existing Writer prompt tests under `backend/tests/basic/`

**Interfaces:**
- Consumes: node service and routing functions from Tasks 3–4.
- Produces: `build_multi_agent_graph()`, compiled graph injection into `SupervisorResearchAgent`, and the unchanged public `arun(question) -> AgentResult`.
- Adds optional `current_date` and `timezone` keyword arguments to `WriterAgent.awrite`; existing callers remain valid.

- [ ] **Step 1: Write a failing graph topology test**

Use a fake node service whose methods append node names and whose replan first returns a ready follow-up and then terminates. Invoke the compiled graph and assert:

```python
assert calls == ["plan", "execute", "replan", "execute", "replan", "writer"]
assert final["termination_reason"] == "completed"
```

Also assert an initial planning failure routes `plan → writer` without execute.

- [ ] **Step 2: Run graph tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_graph.py -q
```

Expected: collection fails because `build_multi_agent_graph` does not exist.

- [ ] **Step 3: Implement the exact StateGraph topology**

Create `graph.py` following the repository's Basic graph dependency-injection pattern:

```python
workflow = StateGraph(MultiAgentGraphState)
workflow.add_node("plan", _plan_node)
workflow.add_node("execute", _execute_node)
workflow.add_node("replan", _replan_node)
workflow.add_node("writer", _writer_node)
workflow.add_edge(START, "plan")
workflow.add_conditional_edges("plan", route_after_plan, {"execute": "execute", "writer": "writer"})
workflow.add_edge("execute", "replan")
workflow.add_conditional_edges("replan", route_after_replan, {"execute": "execute", "writer": "writer"})
workflow.add_edge("writer", END)
return workflow.compile()
```

Each wrapper obtains `MultiAgentWorkflowNodes` from `RunnableConfig["configurable"]["service"]` and raises a clear error if missing.

- [ ] **Step 4: Rewrite `SupervisorResearchAgent.arun` as a graph adapter**

Delete the orchestration `for` loop and nested `run_one`. Build initial state with:

```python
now = datetime.now().astimezone()
initial = {
    "question": question,
    "current_date": now.date().isoformat(),
    "timezone": str(now.tzinfo),
    "tasks": {},
    "ready_task_ids": [],
    "next_task_number": 1,
    "supervisor_iteration": 0,
    "supervisor_circuit_open": False,
    "first_batch": True,
    "final_sufficient": False,
    "final_gaps": [],
    "termination_reason": "",
    "research_context": "",
    "final_sources": [],
    "final_answer": "",
    "events": [],
    "role_usage": UsageBreakdown(),
    "stage_seconds": {},
    "step_count": 0,
    "max_supervisor_iterations": settings.multi_agent_max_supervisor_rounds,
    "sources_before_batch": [],
}
```

Call `graph.ainvoke(initial, {"configurable": {"service": nodes}})`. Build `AgentResult` from final state and runtime snapshots, preserving existing cost estimation and close semantics.

- [ ] **Step 5: Move Writer work into `writer_node` and pass authoritative date**

`writer_node` calls `resources.writer_material(all terminal results, max_chars=30_000)`, determines completed/partial/failed from graph termination state, and calls:

```python
await writer.awrite(
    question=state["question"],
    context=context,
    sources=sources,
    language="zh-CN",
    termination_reason=reason,
    current_date=state["current_date"],
    timezone=state["timezone"],
)
```

Add optional Writer arguments with defaults `None`; include them in the Writer user message only when supplied, so Basic and Deep call signatures and prompts remain backward compatible.

- [ ] **Step 6: Update service construction and agent tests**

`build_multi_agent` creates one compiled graph or accepts the default from `build_multi_agent_graph()`. Rewrite existing agent tests to inject fake node dependencies rather than fake the removed loop. Preserve assertions for `AgentResult`, Writer fallback, event totals, source consistency, and `aclose()`.

- [ ] **Step 7: Run graph/agent/Writer/API tests and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_graph.py tests/multi_agent/test_agent.py tests/multi_agent/test_entrypoints.py tests/basic/test_writer.py tests/basic/test_report_renderer.py -q
uvx ruff check src/deeptrace/multi_agent/graph.py src/deeptrace/multi_agent/agent.py src/deeptrace/multi_agent/service.py src/deeptrace/multi_agent/nodes.py src/deeptrace/prompts/writer.py src/deeptrace/writer/agent.py tests/multi_agent/test_graph.py tests/multi_agent/test_agent.py
git add -- backend/src/deeptrace/multi_agent/graph.py backend/src/deeptrace/multi_agent/agent.py backend/src/deeptrace/multi_agent/service.py backend/src/deeptrace/multi_agent/nodes.py backend/src/deeptrace/prompts/writer.py backend/src/deeptrace/writer/agent.py backend/tests/multi_agent/test_graph.py backend/tests/multi_agent/test_agent.py
git diff --cached --name-only
git commit -m "feat: run supervisor research through LangGraph"
```

### Task 6: Update events/docs, run complete regression, review, and restart

**Files:**
- Modify: `backend/src/deeptrace/static/index.html`
- Modify: `backend/README.md`
- Modify: `README.md`
- Modify: `docs/2026-09-06-supervisor-multi-agent-verification.md`
- Modify: `backend/tests/multi_agent/test_entrypoints.py`

**Interfaces:**
- Consumes: final event names and graph behavior from Tasks 1–5.
- Produces: visible planning/replanning/fallback/finish-rejected events and accurate architecture documentation.

- [ ] **Step 1: Write failing frontend event visibility assertions**

Extend `test_frontend_exposes_multi_agent_mode_and_coordination_events`:

```python
assert "planning.started" in page.text
assert "replanning.started" in page.text
assert "replanning.completed" in page.text
assert "replanning.fallback" in page.text
assert "plan.finish_rejected" in page.text
```

- [ ] **Step 2: Run the frontend test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_entrypoints.py::test_frontend_exposes_multi_agent_mode_and_coordination_events -q
```

Expected: new replanning event names are absent from the frontend major-event set.

- [ ] **Step 3: Update the event set and documentation**

Add the five event names to `MAJOR`. Replace descriptions of the hand-written Supervisor batch loop with the explicit LangGraph topology. Document that current date is injected, insufficient finish is rejected while capacity remains, Provider timeout opens a per-run Supervisor circuit, and final gaps come from leaf tasks.

Update the verification record with automated evidence only. Do not claim real Token/time percentage improvement before a paid comparison run.

- [ ] **Step 4: Run complete automated verification**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src\deeptrace tests
uvx ruff check src/deeptrace/multi_agent tests/multi_agent src/deeptrace/prompts/writer.py src/deeptrace/writer/agent.py
uv lock --check
git diff --check
.\.venv\Scripts\python.exe -m deeptrace.cli --help
```

Expected: all tests pass; scoped Ruff, compile, lock, diff, and the `basic/deep/multi_agent` CLI enum pass. If repository-wide Ruff still has unrelated baseline errors, record the exact count without editing unrelated files.

- [ ] **Step 5: Perform a five-axis code review**

Review tests first, then implementation for correctness, readability, architecture, security, and performance. Explicitly verify:

- no hand-written top-level orchestration loop remains in `multi_agent/agent.py`;
- no graph node can erase existing tasks;
- a valid insufficient finish with open gaps/capacity routes to execute;
- a timeout causes one Provider attempt, not two;
- parent gaps disappear only after a child task exists, and child gaps remain visible;
- cancellation releases leases and does not start Writer;
- external page text and Provider errors remain untrusted and sanitized;
- Basic and Deep tests remain unchanged and green.

- [ ] **Step 6: Restart only the verified local backend process**

Resolve the PID listening on `127.0.0.1:8000`, verify its command line contains `-m deeptrace.api`, stop that child and its matching launcher only, then start:

```powershell
Start-Process `
  -FilePath "D:\Dev\Projects\agent_new\backend\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "deeptrace.api" `
  -WorkingDirectory "D:\Dev\Projects\agent_new\backend" `
  -WindowStyle Hidden `
  -RedirectStandardOutput "D:\Dev\Projects\agent_new\backend\server.stdout.log" `
  -RedirectStandardError "D:\Dev\Projects\agent_new\backend\server.stderr.log"
```

Poll `/openapi.json` and `/`; verify the mode enum is exactly `basic,deep,multi_agent` and the page contains `plan.finish_rejected`. Do not submit a research request.

- [ ] **Step 7: Stage only reviewed final files and commit**

Run `git status --short` and inspect `git diff --cached --name-only`. Stage only files named in this plan that are not inseparably mixed with unrelated user edits. Commit:

```powershell
git commit -m "docs: verify LangGraph supervisor research"
```

If a shared dirty file contains unrelated changes that cannot be separated safely, leave that file uncommitted and report it rather than absorbing the user's work.

## Plan Self-Review

- Spec coverage: Task 1 implements the persistent ledger; Task 2 handles planning/replanning, compact history, date input, timeout and deterministic fallback; Tasks 3–4 implement parallel execution and termination invariants; Task 5 compiles the graph and preserves public output/Writer behavior; Task 6 covers frontend, documentation, review, regression and restart.
- Completeness scan: every behavior-changing task includes a literal failing assertion, expected RED reason, minimal production interface, GREEN command, and commit boundary; no unfinished instruction markers remain.
- Type consistency: `PlannedTask`, `MultiAgentGraphState`, `SupervisorOutcome`, `MultiAgentWorkflowNodes`, `build_multi_agent_graph`, routing function names, graph state keys and optional Writer date arguments are defined before later tasks consume them.
- Scope: Basic and Deep remain untouched; existing Researcher/tool/resource policies are reused; no new dependency or evidence-object pipeline is introduced.
