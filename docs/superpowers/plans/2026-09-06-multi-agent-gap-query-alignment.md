# Multi-Agent Gap-to-Query Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve each unresolved leaf gap through follow-up planning and require every Researcher tool action to identify the exact checklist item it serves.

**Architecture:** Keep the existing LangGraph Supervisor/Researcher/Writer topology. Add a deterministic gap compiler at the replan boundary, use exact gap text as the child assignment identity, and add assignment-aware validation before Researcher tools execute. Initial research may establish broad context for a selected checklist item; follow-up research receives a one-gap assignment and must search that gap directly.

**Tech Stack:** Python 3.12, Pydantic v2, LangGraph/LangChain messages and tool schemas, pytest, Ruff, uv.

**Spec:** `docs/superpowers/specs/2026-09-06-multi-agent-gap-query-alignment-design.md`

## Global Constraints

- Modify only Multi-Agent behavior and its documentation; do not change Basic or Deep execution semantics.
- Do not increase Supervisor rounds, Researcher rounds, researcher count, or tool-call limits.
- Do not add an Agent role, an LLM call, Critic, Verifier, Claim, Evidence, or `ResearchNote`.
- Writer continues to consume webpage text or BGE-selected original text only.
- Alignment rejection must occur before `ResearcherTools.execute`, so it cannot consume network quota.
- Do not run a real Provider-backed research request during automated verification.
- Preserve all unrelated dirty and untracked worktree files.

---

### Task 1: Preserve Gap Lineage and Compile One-Gap Follow-Ups

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/state.py`
- Modify: `backend/src/deeptrace/multi_agent/supervisor.py`
- Test: `backend/tests/multi_agent/test_state.py`
- Test: `backend/tests/multi_agent/test_supervisor.py`

**Interfaces:**
- Produces: `leaf_gap_records(tasks: Mapping[str, PlannedTask]) -> list[tuple[str, str]]`, returning stable `(task_id, gap)` pairs that have not been covered by an executed child.
- Changes: `build_gap_followups(history: list[dict], *, max_assignments: int, preferred_assignments: list[AssignmentDraft] | None = None) -> list[AssignmentDraft]`.
- Invariant: a child covers a parent gap only when the child `required_outputs` contains that exact gap and the child has executed.

- [ ] **Step 1: Write failing state-ledger tests**

Add tests proving that a child covering one of two parent gaps does not hide the other, while a child covering both legacy outputs through two separate assignments hides both:

```python
def test_child_supersedes_only_the_exact_parent_gap():
    tasks = {
        "r1": PlannedTask(
            assignment=assignment("r1"),
            status="partial",
            result=result(
                "r1",
                "partial",
                ("巴黎峰会成果未确认", "欧盟法案实施未确认"),
            ),
        ),
        "r2": PlannedTask(
            assignment=assignment(
                "r2",
                parents=("r1",),
                required_outputs=("巴黎峰会成果未确认",),
            ),
            status="completed",
            result=result("r2", "completed"),
        ),
    }
    assert leaf_gaps(tasks) == ["欧盟法案实施未确认"]
```

Extend the existing test helper with an optional `required_outputs` tuple and update the two existing follow-up supersession tests to pass the exact parent gap. This makes their old task-level assumption explicit under the new per-gap contract.

- [ ] **Step 2: Run the state test and verify RED**

Run:

```powershell
uv run pytest tests/multi_agent/test_state.py -q
```

Expected: the uncovered parent gap disappears under the current task-level supersession logic.

- [ ] **Step 3: Implement exact gap lineage**

Compute covered parent gaps from executed child assignments, then filter each task result gap independently:

```python
def leaf_gap_records(tasks: Mapping[str, PlannedTask]) -> list[tuple[str, str]]:
    covered = {
        (parent_id, required_output)
        for child in tasks.values()
        if child.result is not None
        for parent_id in child.assignment.parent_ids
        for required_output in child.assignment.required_outputs
    }
    records = []
    for task_id, task in tasks.items():
        if task.result is None or task.status not in {"partial", "blocked"}:
            continue
        for gap in task.result.gaps:
            if (task_id, gap) not in covered:
                records.append((task_id, gap))
    return records
```

Make `leaf_gaps` deduplicate the gap strings from these records. Keep `open_leaf_tasks` compatible by returning tasks with at least one remaining record.

- [ ] **Step 4: Write failing follow-up compiler tests**

Cover these behaviors:

```python
def test_gap_followups_create_one_assignment_per_gap():
    history = partial_history()[:1]
    history[0]["gaps"] = ["巴黎峰会成果未确认", "欧盟法案实施未确认"]
    followups = build_gap_followups(history, max_assignments=2)
    assert [item.required_outputs for item in followups] == [
        ["巴黎峰会成果未确认"],
        ["欧盟法案实施未确认"],
    ]
    assert [item.objective for item in followups] == [
        "补充并核实：巴黎峰会成果未确认",
        "补充并核实：欧盟法案实施未确认",
    ]

def test_broad_supervisor_draft_only_prioritizes_parent_and_cannot_replace_gap():
    preferred = [AssignmentDraft(
        objective="整理全球AI政策热点",
        required_outputs=["完成政策整理"],
        parent_ids=["r1"],
    )]
    followups = build_gap_followups(
        history, max_assignments=1, preferred_assignments=preferred
    )
    assert followups[0].required_outputs == ["巴黎峰会成果未确认"]
```

- [ ] **Step 5: Run the compiler tests and verify RED**

Run:

```powershell
uv run pytest tests/multi_agent/test_supervisor.py -q
```

Expected: current code groups multiple gaps into one output and has no preferred-assignment input.

- [ ] **Step 6: Implement the deterministic compiler**

Replace task-level grouping with stable gap records. Use valid `preferred_assignments[].parent_ids` to order parents; use exact matches in their `required_outputs` to order a parent's gaps; append all unselected records afterward. Emit one `AssignmentDraft` per selected record:

```python
AssignmentDraft(
    objective=f"补充并核实：{gap}",
    required_outputs=[gap],
    excluded_scope=_bounded_unique(parent_excluded_scope, "不重复已确认内容"),
    source_guidance=_bounded_unique(parent_source_guidance, "优先官方或一手来源"),
    parent_ids=[parent_id],
)
```

- [ ] **Step 7: Run Task 1 tests and commit**

Run:

```powershell
uv run pytest tests/multi_agent/test_state.py tests/multi_agent/test_supervisor.py -q
uvx ruff check src/deeptrace/multi_agent/state.py src/deeptrace/multi_agent/supervisor.py tests/multi_agent/test_state.py tests/multi_agent/test_supervisor.py
```

Commit only Task 1 files:

```powershell
git add -- backend/src/deeptrace/multi_agent/state.py backend/src/deeptrace/multi_agent/supervisor.py backend/tests/multi_agent/test_state.py backend/tests/multi_agent/test_supervisor.py
git commit -m "fix: preserve exact gaps in follow-up tasks"
```

---

### Task 2: Add Checklist Identity to Research Tool Calls

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/models.py`
- Modify: `backend/src/deeptrace/multi_agent/tools.py`
- Test: `backend/tests/multi_agent/test_models.py`
- Test: `backend/tests/multi_agent/test_tools.py`

**Interfaces:**
- Produces: `TargetedResearchTopicArgs`, `TargetedFetchArgs`, and `TargetedSearchArgs`, each with required `target_output: Text`.
- `RESEARCHER_MODEL_TOOLS` exposes targeted schemas for `research_topic`, `fetch_page`, and `search_memory`.
- `ResearcherTools.execute` accepts these targeted arguments while internal `_search`, `_fetch`, and `_memory_search` continue to use the existing base argument fields.

- [ ] **Step 1: Write failing tool-schema tests**

Assert that every tool exposed to the Researcher model requires `target_output`, while the hidden `search_web` helper remains unchanged:

```python
def test_researcher_model_tools_require_target_output():
    for tool in RESEARCHER_MODEL_TOOLS:
        required = tool["function"]["parameters"]["required"]
        assert "target_output" in required
```

Add a `ResearcherTools.execute` test with a targeted `research_topic` call and verify that the underlying search receives only its Query semantics and completes normally.

- [ ] **Step 2: Run model/tool tests and verify RED**

Run:

```powershell
uv run pytest tests/multi_agent/test_models.py tests/multi_agent/test_tools.py -q
```

Expected: current tool schemas contain no `target_output`.

- [ ] **Step 3: Add targeted argument models and schemas**

Keep internal base models and add focused subclasses:

```python
class TargetedSearchArgs(SearchArgs):
    target_output: Text

class TargetedResearchTopicArgs(ResearchTopicArgs):
    target_output: Text

class TargetedFetchArgs(FetchArgs):
    target_output: Text
```

Use those models only for Researcher-visible tools. Keep `search_web` on `SearchArgs` because it is not exposed by `RESEARCHER_MODEL_TOOLS`.

- [ ] **Step 4: Update tool parsing without changing network behavior**

Map the three Researcher-visible names to targeted schemas in `ResearcherTools.execute`. Handler methods may accept the subclasses because they retain `query`, `url`, `refresh`, and `max_pages`. Internal recursive calls continue constructing the non-targeted base models.

- [ ] **Step 5: Update existing fixture calls and verify GREEN**

Add a valid `target_output` to existing direct tests of Researcher-visible tools. Do not add it to internal `search_web` tests.

Run:

```powershell
uv run pytest tests/multi_agent/test_models.py tests/multi_agent/test_tools.py -q
uvx ruff check src/deeptrace/multi_agent/models.py src/deeptrace/multi_agent/tools.py tests/multi_agent/test_models.py tests/multi_agent/test_tools.py
```

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- backend/src/deeptrace/multi_agent/models.py backend/src/deeptrace/multi_agent/tools.py backend/tests/multi_agent/test_models.py backend/tests/multi_agent/test_tools.py
git commit -m "feat: bind research tools to checklist outputs"
```

---

### Task 3: Reject Misaligned Actions Before Network Execution

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/prompts.py`
- Modify: `backend/src/deeptrace/multi_agent/researcher.py`
- Test: `backend/tests/multi_agent/test_researcher.py`

**Interfaces:**
- Researcher validates `call["args"]["target_output"] in assignment.required_outputs` before calling `tools.execute`.
- Rejected actions emit `tool.rejected` with scalar `task_id`, `tool`, `target_output`, and `reason_code="unknown_target_output"`.
- A successful tool result marks the selected output `researched` in task-local progress only.

- [ ] **Step 1: Write failing rejection tests**

Add a tracking tool whose `execute` increments a counter. Test both missing and unknown targets:

```python
def test_unknown_target_output_is_rejected_before_tool_execution():
    model = ScriptedModel([
        call("research_topic", {
            "target_output": "不属于任务的检查项",
            "query": "宽泛查询",
            "max_pages": 1,
        }),
        call("finish_research", partial_finish_args()),
    ])
    tools = TrackingTools()
    runtime = MultiAgentRuntime(settings(2))
    result = asyncio.run(Researcher(model, runtime).run(assignment(), tools))
    assert tools.execute_calls == 0
    assert any(
        event.event_type == "tool.rejected"
        and event.details["reason_code"] == "unknown_target_output"
        for event in runtime.events
    )
```

Also assert that a rejected call does not change `lease.used`.

- [ ] **Step 2: Run rejection tests and verify RED**

Run:

```powershell
uv run pytest tests/multi_agent/test_researcher.py -q
```

Expected: current Researcher executes the tool without assignment-aware validation.

- [ ] **Step 3: Implement pre-execution validation**

After limiting a batch to the first tool call and before `run_tool`, validate the scalar target. For an invalid target, append an `AIMessage` plus matching `ToolMessage` containing only a sanitized error and allowed outputs, emit `tool.rejected`, and continue to the next model decision without calling `tools.execute`.

- [ ] **Step 4: Write failing prompt-mode and progress tests**

Assert:

```python
assert "initial assignment" in initial_prompt
assert "broad context" in initial_prompt
assert "follow-up assignment" in followup_prompt
assert "do not restart broad topic research" in followup_prompt
assert "Not yet researched outputs" in second_round_prompt
```

The follow-up fixture must have `parent_ids=["r1"]` and exactly one required output.

- [ ] **Step 5: Run prompt tests and verify RED**

Run the new tests individually and confirm the mode-specific text and progress are missing.

- [ ] **Step 6: Implement mode-specific prompts and task-local progress**

Pass `is_followup=bool(assignment.parent_ids)` into the prompt builder. Initial mode may establish context for its selected output; follow-up mode must state that the first query directly targets its single unresolved output and must not restart broad topic research.

Maintain:

```python
researched_outputs: set[str] = set()
```

After a successful tool result, add its `target_output`. Before each decision, include stable JSON lists for `not_yet_researched_outputs` and `researched_outputs`. Do not call this evidence or mark an output supported solely because a tool returned `ok`.

- [ ] **Step 7: Record target-aware tool events**

Change `tool.started` to include the selected output in both the message and scalar details:

```python
self.runtime.emit(
    "tool.started",
    f"{assignment.id} 针对检查项「{target_output}」调用 {call['name']}：...",
    task_id=assignment.id,
    tool=call["name"],
    target_output=target_output,
)
```

- [ ] **Step 8: Update existing Researcher fixtures and verify GREEN**

Every scripted Researcher-visible research call must include `target_output="代表性进展"`. Finish calls remain unchanged.

Run:

```powershell
uv run pytest tests/multi_agent/test_researcher.py -q
uvx ruff check src/deeptrace/multi_agent/prompts.py src/deeptrace/multi_agent/researcher.py tests/multi_agent/test_researcher.py
```

- [ ] **Step 9: Commit Task 3**

```powershell
git add -- backend/src/deeptrace/multi_agent/prompts.py backend/src/deeptrace/multi_agent/researcher.py backend/tests/multi_agent/test_researcher.py
git commit -m "fix: reject research actions outside assigned outputs"
```

---

### Task 4: Integrate Exact Follow-Ups into the LangGraph Replan Node

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/nodes.py`
- Test: `backend/tests/multi_agent/test_nodes.py`
- Test: `backend/tests/multi_agent/test_agent.py`

**Interfaces:**
- Replan uses Supervisor drafts only as prioritization hints and dispatches `build_gap_followups(...)` output.
- Initial planning continues to use the Supervisor's original independent assignments.
- Public events keep the existing `RunEvent.details` scalar type.

- [ ] **Step 1: Write failing replan integration test**

Give the Supervisor a broad follow-up draft for a parent with two concrete gaps. Assert that the resulting tasks use exact gaps and one output each:

```python
assert update["tasks"]["r2"].assignment.required_outputs == [
    "巴黎峰会成果未确认"
]
assert update["tasks"]["r2"].assignment.objective == (
    "补充并核实：巴黎峰会成果未确认"
)
```

With two available slots, assert both gaps become sibling tasks with `parent_ids=["r1"]`.

- [ ] **Step 2: Run node test and verify RED**

Run:

```powershell
uv run pytest tests/multi_agent/test_nodes.py -q
```

Expected: current code inserts `decision.assignments` directly.

- [ ] **Step 3: Compile Supervisor drafts at the replan boundary**

For `decision.action == "dispatch"`, replace direct slicing with:

```python
drafts = build_gap_followups(
    compact_task_history(tasks),
    max_assignments=max_assignments,
    preferred_assignments=decision.assignments,
)
```

Keep the existing deterministic compiler path for rejected finish decisions, now benefiting from the same one-gap behavior.

- [ ] **Step 4: Write failing observability tests**

Assert `researcher.started.details` contains:

```python
assert json.loads(event.details["required_outputs"]) == ["巴黎峰会成果未确认"]
assert event.details["parent_ids"] == "r1"
```

Also assert the `replanning.completed` message contains the concrete gap-derived objective.

- [ ] **Step 5: Run observability tests and verify RED**

Run the new tests individually; current start events do not contain `required_outputs`.

- [ ] **Step 6: Add scalar-compatible event mapping**

Serialize `required_outputs` with `json.dumps(..., ensure_ascii=False)` and keep `parent_ids` comma-separated. Add the same fields to queued and started events so queued work is also inspectable.

- [ ] **Step 7: Run Multi-Agent integration tests and commit**

Run:

```powershell
uv run pytest tests/multi_agent/test_nodes.py tests/multi_agent/test_agent.py -q
uvx ruff check src/deeptrace/multi_agent/nodes.py tests/multi_agent/test_nodes.py tests/multi_agent/test_agent.py
```

Commit:

```powershell
git add -- backend/src/deeptrace/multi_agent/nodes.py backend/tests/multi_agent/test_nodes.py backend/tests/multi_agent/test_agent.py
git commit -m "feat: dispatch exact gap-aligned follow-ups"
```

---

### Task 5: Documentation, Full Regression, and Local Restart

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/2026-09-06-supervisor-multi-agent-verification.md`

**Interfaces:**
- Documents the exact parent-gap-to-query mapping, initial/follow-up distinction, and quota-neutral rejection.
- Does not claim a measured Token or latency reduction without a paid comparison run.

- [ ] **Step 1: Run the complete Multi-Agent suite**

```powershell
Set-Location D:\Dev\Projects\agent_new\backend
uv run pytest tests/multi_agent -q
```

Expected: all Multi-Agent tests pass without network or Provider calls.

- [ ] **Step 2: Run full repository verification**

```powershell
uv run pytest -q
uvx ruff check src/deeptrace/multi_agent tests/multi_agent
uv run python -m compileall -q src tests
uv lock --check
```

Record the exact test count. If broader Ruff reports unrelated baseline files, run and report the scoped command without modifying unrelated code.

- [ ] **Step 3: Update documentation**

Document:

- one unresolved gap becomes one follow-up Assignment;
- a child supersedes only its exact parent gap;
- every Researcher-visible research action carries `target_output`;
- initial tasks may establish context, follow-ups directly target their gap;
- invalid target actions are rejected before network quota use;
- no new LLM call or increased execution limit was introduced.

- [ ] **Step 4: Review changed code before merge**

Use the code-review-and-quality skill. Inspect correctness, task-ledger lineage, malformed tool-call handling, event serialization, security of emitted content, performance, and dead code. Apply only fixes directly required by this feature, with a failing test before behavior changes.

- [ ] **Step 5: Commit documentation separately**

```powershell
git add -- README.md backend/README.md docs/2026-09-06-supervisor-multi-agent-verification.md
git commit -m "docs: verify gap-aligned multi-agent research"
```

- [ ] **Step 6: Restart and health-check the local API**

Resolve the exact process listening on `127.0.0.1:8000`, verify its command line contains `-m deeptrace.api` and its launcher is inside `D:\Dev\Projects\agent_new\backend`, stop only that verified process pair, and restart hidden with the backend virtual environment. Verify `/` and `/openapi.json` return HTTP 200.

Do not submit a research request. Open `http://127.0.0.1:8000/` for the user's manual test.

- [ ] **Step 7: Final scope audit**

```powershell
git diff --check
git status --short
git log -8 --oneline
```

Confirm each feature commit contains only its listed files and all pre-existing unrelated dirty/untracked work remains untouched.
