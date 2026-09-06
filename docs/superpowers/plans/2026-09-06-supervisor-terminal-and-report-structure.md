# Supervisor Terminal Short-Circuit and Report Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate unnecessary final Supervisor calls and produce better-structured reports whose Chinese source section is titled “参考内容”.

**Architecture:** Keep the compiled LangGraph topology unchanged. Move decisions already determined by leaf-task state and hard limits ahead of the Supervisor Provider boundary, then strengthen the existing single-pass Writer contract and update only the deterministic renderer label.

**Tech Stack:** Python 3.12, LangGraph, Pydantic, LangChain messages, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-06-supervisor-terminal-and-report-structure-design.md`

## Global Constraints

- Do not add a Critic, Editor, second Writer call, or another model role.
- Do not change Researcher rounds, researcher count, tool-call limits, Token accounting, or the LangGraph topology.
- Keep Writer fact input as original page text or BGE-selected original excerpts; do not introduce `ResearchNote`, Claim, Evidence, or Verifier objects.
- Time and Token remain observation only; loop and tool-call counts remain stop boundaries.
- Chinese reports use “参考内容”; English reports continue to use `References`.
- Do not run a paid Provider/Tavily research request during automated verification.

---

### Task 1: Short-circuit deterministic replan outcomes before the Supervisor call

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/nodes.py`
- Modify: `backend/tests/multi_agent/test_nodes.py`

**Interfaces:**
- Consumes: `leaf_gaps(tasks)`, `task_source_urls(tasks)`, `resources.quota.remaining`, `multi_agent_max_researchers`, `max_supervisor_iterations`, and the existing state keys.
- Produces: `MultiAgentWorkflowNodes._finish_replan(...) -> dict` and a `replan_node` that calls `supervisor.replan` only when a follow-up can still be dispatched.

- [ ] **Step 1: Add the exact final-round regression from run `68891660c219`**

Add a test with r1 completed and r5 partial, `supervisor_iteration=2`, `max_supervisor_iterations=3`, available researcher slots, and at least two remaining network attempts:

```python
def test_replan_skips_supervisor_when_no_followup_round_remains():
    async def scenario():
        tasks = {
            "r1": terminal_task("r1", status="completed"),
            "r5": terminal_task(
                "r5",
                gaps=["联合国全球AI治理对话机制成立月份未明确"],
                parents=("r3",),
            ),
        }
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="finish",
                    rationale="不应调用",
                    sufficient=False,
                    gaps=["不应使用"],
                )
            )
        )
        current_settings = settings()
        runtime = MultiAgentRuntime(current_settings)
        nodes = MultiAgentWorkflowNodes(
            model=object(), writer=Writer(), resources=Resources(),
            settings=current_settings, runtime=runtime, supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["next_task_number"] = 6
        state["supervisor_iteration"] = 2
        state["first_batch"] = False
        update = await nodes.replan_node(state)
        assert supervisor.calls == 0
        assert update["termination_reason"] == "supervisor_round_limit"
        assert update["final_gaps"] == [
            "联合国全球AI治理对话机制成立月份未明确"
        ]
        assert not any(
            event.event_type in {"supervisor.retry", "supervisor.fallback"}
            for event in runtime.events
        )

    asyncio.run(scenario())
```

- [ ] **Step 2: Add deterministic completion and hard-limit tests**

Update `test_replan_finishes_when_completed_tasks_have_no_open_gaps` to assert `supervisor.calls == 0`. Update the researcher-limit test to assert the same. Add a quota test using `Resources().quota.consumed = 29` and assert `global_tool_limit`, the exact leaf gap, and zero Supervisor calls. In the existing actionable early-finish test, assert `supervisor.calls == 1` so the short circuit cannot suppress valid replanning.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_nodes.py -k "skips_supervisor or no_open_gaps or researcher_limit or global_tool_limit" -q
```

Expected: the final-round, no-gap, researcher-limit, and quota tests report `supervisor.calls == 1` because the current node invokes the Provider before applying deterministic termination.

- [ ] **Step 4: Extract one deterministic terminal-update helper**

Add this method to `MultiAgentWorkflowNodes` and use it for all replan terminal branches:

```python
def _finish_replan(
    self,
    state: dict,
    *,
    tasks: dict,
    gaps: list[str],
    reason: str,
    sufficient: bool = False,
) -> dict:
    self.runtime.emit(
        "replanning.completed",
        "主管结束研究，检查项已满足"
        if sufficient
        else "主管结束研究并保留未解决问题",
        termination_reason=reason,
        sufficient=sufficient,
    )
    return {
        "tasks": tasks,
        "ready_task_ids": [],
        "supervisor_iteration": int(state["supervisor_iteration"]),
        "final_sufficient": sufficient,
        "final_gaps": gaps,
        "termination_reason": reason,
        **self._telemetry(),
    }
```

This helper must not increment `supervisor_iteration`, because no Supervisor decision occurred.

- [ ] **Step 5: Apply the ordered pre-call termination policy**

Move `replanning.started` to the beginning of `replan_node`, then return before `supervisor.replan` in this exact order:

```python
if has_followup and gaps and not (current_sources - previous_sources):
    return self._finish_replan(
        state, tasks=tasks, gaps=gaps, reason="stagnant"
    )
if not gaps:
    return self._finish_replan(
        state, tasks=tasks, gaps=[], reason="completed", sufficient=True
    )
if remaining_slots <= 0:
    return self._finish_replan(
        state, tasks=tasks, gaps=gaps, reason="researcher_limit"
    )
if self.resources.quota.remaining < 2:
    return self._finish_replan(
        state, tasks=tasks, gaps=gaps, reason="global_tool_limit"
    )
if not decision_has_followup_round:
    return self._finish_replan(
        state, tasks=tasks, gaps=gaps, reason="supervisor_round_limit"
    )
```

After these guards, `can_dispatch` is always true. Keep the existing invalid-structure repair, deterministic gap fallback, premature-finish rejection, stable task IDs, and circuit breaker unchanged.

- [ ] **Step 6: Run Task 1 tests and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_nodes.py tests/multi_agent/test_graph.py tests/multi_agent/test_agent.py tests/multi_agent/test_supervisor.py -q
uvx ruff check src/deeptrace/multi_agent/nodes.py tests/multi_agent/test_nodes.py
```

Expected: all selected tests pass and Ruff reports `All checks passed!`.

Commit only the two Task 1 files:

```powershell
git add -- backend/src/deeptrace/multi_agent/nodes.py backend/tests/multi_agent/test_nodes.py
git diff --cached --name-only
git commit -m "fix: skip terminal supervisor reviews"
```

---

### Task 2: Enforce a complete single-pass Writer structure and rename the Chinese source section

**Files:**
- Modify: `backend/src/deeptrace/prompts/writer.py`
- Modify: `backend/src/deeptrace/writer/renderer.py`
- Modify: `backend/tests/basic/test_writer.py`
- Modify: `backend/tests/basic/test_report_renderer.py`

**Interfaces:**
- Consumes: `build_writer_messages(...)`, `WriterAgent.awrite(...)`, and `render_report(markdown, sources, language)`.
- Produces: a stronger `WRITER_SYSTEM_PROMPT` and Chinese rendered reports ending in `参考内容\n\n[1] URL`.

- [ ] **Step 1: Write the failing Writer structure-contract test**

Add to `tests/basic/test_writer.py`:

```python
def test_writer_prompt_requires_overview_transitions_limitations_and_conclusion():
    model = ScriptedModel([
        "报告\n\n1 总述\n\n概括 [[source:1]]。\n\n"
        "2 分析\n\n承接分析 [[source:1]]。\n\n"
        "3 综合结论\n\n综合判断 [[source:1]]。"
    ])
    _run(
        WriterAgent(model).awrite(
            question="研究问题",
            context=CONTEXT,
            sources=["https://example.com/a"],
            language="zh-CN",
        )
    )
    system = model.messages[-1][0].content
    assert "1 总述" in system
    assert "two to three paragraphs" in system
    assert "transition" in system.lower()
    assert "研究局限" in system
    assert "only when" in system.lower()
    assert "综合结论" in system
    assert "final body section" in system.lower()
    assert "Do not introduce facts" in system
```

- [ ] **Step 2: Update renderer tests to require “参考内容” and preserve English**

Replace every Chinese expected separator `参考文献` with `参考内容` in `tests/basic/test_report_renderer.py` and `tests/basic/test_writer.py`. Add an explicit stripping regression:

```python
def test_renderer_replaces_model_reference_content_section():
    report = render_report(
        "报告\n\n1 总述\n\n结论 [[source:1]]。\n\n"
        "参考内容\n\n[1] 模型自行输出的来源",
        SOURCES,
        "zh-CN",
    )
    assert report == (
        "报告\n\n1 总述\n\n结论 [1]。\n\n"
        "参考内容\n\n[1] https://example.com/a"
    )
```

Retain the existing English assertion that the heading is `References`.

- [ ] **Step 3: Run the Writer/renderer tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/basic/test_writer.py tests/basic/test_report_renderer.py -q
```

Expected: the prompt assertions fail because the structure contract is absent, Chinese separator assertions fail because the renderer still emits `参考文献`, and the new stripping test duplicates the model-generated `参考内容` section.

- [ ] **Step 4: Strengthen the existing Writer system prompt without adding a call**

Append these requirements to `WRITER_SYSTEM_PROMPT` before `Return only the report body`:

```python
"For a Chinese report, the required body structure is: a plain title; "
"1 总述 with two to three paragraphs that directly answer the question and "
"synthesize the major findings; numbered thematic sections; 研究局限 only when "
"the supplied termination reason identifies material unresolved gaps; and 综合结论 "
"as the final body section. Begin every major thematic section with a synthesis "
"or transition paragraph before presenting details. The conclusion must connect "
"multiple themes and must not merely repeat the overview. Do not introduce facts "
"in the conclusion that are absent from the supplied context. "
```

Do not add prompt validation, a Writer retry for missing sections, or another Provider call.

- [ ] **Step 5: Update deterministic Chinese source rendering**

Change the reference-section matcher and heading in `writer/renderer.py`:

```python
_REFERENCE_SECTION = re.compile(
    r"(?ims)^\s*#{0,6}\s*(?:参考内容|参考文献|references)\s*$.*\Z"
)

heading = "参考内容" if language.lower().startswith("zh") else "References"
```

Keeping `参考文献` in the stripping regex is intentional backward compatibility for model output and saved prompt variants; the renderer itself must emit only `参考内容` for Chinese.

- [ ] **Step 6: Run Task 2 tests and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/basic/test_writer.py tests/basic/test_report_renderer.py tests/multi_agent/test_nodes.py -q
uvx ruff check src/deeptrace/prompts/writer.py src/deeptrace/writer/renderer.py tests/basic/test_writer.py tests/basic/test_report_renderer.py
```

Expected: all selected tests and Ruff pass.

Because `prompts/writer.py` contains unrelated existing working-tree edits, stage only the new structure-contract hunk for that tracked file. Stage the renderer and test files only if their full diffs are limited to this report-format change. Commit:

```powershell
git diff --cached --name-only
git commit -m "feat: structure reports with overview and conclusion"
```

---

### Task 3: Update documentation, perform full review, and restart the verified backend

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/2026-09-06-supervisor-multi-agent-verification.md`

**Interfaces:**
- Consumes: final behavior and exact test counts from Tasks 1–2.
- Produces: accurate user-facing documentation, an updated verification record, and a live backend at `http://127.0.0.1:8000/`.

- [ ] **Step 1: Update user-facing report and Supervisor descriptions**

Document these exact behaviors:

- hard terminal boundaries bypass the Supervisor Provider call;
- actionable gaps still use Supervisor replanning and deterministic fallback;
- Chinese reports contain `1 总述`, thematic transitions, optional `研究局限`, final `综合结论`, and a `参考内容` URL section;
- no additional Writer/Critic call was added;
- observed Token savings are not claimed until a paid comparison run exists.

- [ ] **Step 2: Run complete automated verification**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src\deeptrace tests
uvx ruff check src/deeptrace/multi_agent tests/multi_agent src/deeptrace/prompts/writer.py src/deeptrace/writer
uv lock --check
git diff --check
.\.venv\Scripts\python.exe -m deeptrace.cli --help
```

Record the exact pytest count in `docs/2026-09-06-supervisor-multi-agent-verification.md`. Do not run an actual research request.

- [ ] **Step 3: Perform the five-axis code review**

Review tests before implementation, then verify:

- correctness: every deterministic terminal state skips `supervisor.replan`, while actionable capacity still reaches it;
- readability: terminal-update construction is centralized instead of duplicated;
- architecture: LangGraph edges, state model, Researcher behavior, and Writer call count remain unchanged;
- security: Provider validation details and external page text are not copied into user-visible error events;
- performance: terminal states remove Provider calls and no new unbounded loop or model call exists;
- dead code: list any newly unreachable compatibility helpers, but do not delete uncertain compatibility code without user approval.

- [ ] **Step 4: Restart only the verified local backend**

Resolve the process listening on `127.0.0.1:8000`. Verify its command line contains `-m deeptrace.api`, stop that process and its matching launcher only, then start:

```powershell
Start-Process `
  -FilePath "D:\Dev\Projects\agent_new\backend\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "deeptrace.api" `
  -WorkingDirectory "D:\Dev\Projects\agent_new\backend" `
  -WindowStyle Hidden `
  -RedirectStandardOutput "D:\Dev\Projects\agent_new\backend\server.stdout.log" `
  -RedirectStandardError "D:\Dev\Projects\agent_new\backend\server.stderr.log"
```

Poll `/openapi.json` and `/`. Assert HTTP 200, mode enum `basic,deep,multi_agent`, and frontend availability. Do not submit a research question.

- [ ] **Step 5: Commit only reviewed documentation**

Inspect `git status --short` and `git diff --cached --name-only`. Stage only documentation hunks belonging to this change, then commit:

```powershell
git commit -m "docs: verify terminal research and report format"
```

## Plan Self-Review

- Spec coverage: Task 1 implements all six ordered Supervisor guards and preserves actionable fallback; Task 2 implements the single-pass report structure and Chinese `参考内容`; Task 3 covers documentation, full verification, review, and restart.
- Placeholder scan: every implementation, error path, command, expected failure, and commit boundary is explicit.
- Type consistency: every state key, class, method, termination reason, prompt builder, and renderer signature matches the current repository definitions.
- Scope: no new dependency, agent role, model call, evidence object, quota, or graph edge is introduced.
