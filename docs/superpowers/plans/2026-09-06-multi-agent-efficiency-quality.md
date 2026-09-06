# Multi-Agent Efficiency and Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `multi_agent` produce more usable source-grounded reports with fewer repeated searches, smaller model contexts, accurate concurrency events, and diagnosable Supervisor fallbacks without changing Basic or Deep.

**Architecture:** Keep Supervisor and independent ReAct Researchers, but programmatically bound each Researcher to one useful research tool per decision and two research decisions plus a reserved closeout. Trim navigation payloads before they enter model history, preserve larger BGE-selected original context only for Writer, and make Supervisor/scheduler failures explicit and recoverable.

**Tech Stack:** Python 3.12 in the current environment, asyncio, Pydantic v2, LangChain tool messages, existing Tavily/scraper/BGE/Writer, FastAPI/SSE, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-06-multi-agent-efficiency-quality-design.md`

## Global Constraints

- Modify only `multi_agent` behavior plus its settings, prompts, documentation, and frontend event list; do not alter Basic or Deep execution.
- Keep time, Token, and estimated cost observational only.
- Keep the total network attempt default at 30, per-Researcher cap at 10, reserve ratio at 20%, and Supervisor rounds at 3.
- Do not add ResearchNote, Claim, Evidence, Verifier, per-page LLM summaries, a new Agent framework, or a third-party dependency.
- Writer facts must continue to come from BGE-selected original page text, never from task summaries.
- Preserve numbered report headings, first-use numeric citations, and reference URLs at the end.
- Do not run a paid real-provider benchmark without explicit user authorization.

---

### Task 1: Bound Researcher decisions and navigation payloads

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/models.py`
- Modify: `backend/src/deeptrace/multi_agent/researcher.py`
- Modify: `backend/src/deeptrace/multi_agent/tools.py`
- Modify: `backend/src/deeptrace/multi_agent/resources.py`
- Test: `backend/tests/multi_agent/test_researcher.py`
- Test: `backend/tests/multi_agent/test_tools.py`

**Interfaces:**
- Consumes: `Researcher.run(assignment, tools) -> ResearcherResult`, `ResearcherTools.execute(name, args) -> dict`, `SharedResearchResources.writer_material(results, max_chars=...)`.
- Produces: `RESEARCHER_MODEL_TOOLS` containing `research_topic`, `fetch_page`, `search_memory`, and `finish_research`; `search_web` remains executable internally but is absent from model bindings.
- Produces: at most one executed research tool per model decision, with `tool.batch_limited` when extra calls are ignored.
- Produces: search payloads capped at 3 results × 300 snippet characters, Researcher page context capped at 1,200 characters, and Writer material capped by a 3,000-character per-source ceiling.

- [ ] **Step 1: Write failing tool-boundary tests**

Add literal assertions to `test_tools.py`:

```python
def test_search_payload_is_navigation_sized(raw_document):
    # Fake search returns five 1,000-character snippets.
    # Execute the real ResearcherTools search boundary.
    assert len(result["results"]) == 3
    assert all(len(item["snippet"]) <= 300 for item in result["results"])

def test_fetch_payload_is_smaller_than_writer_context(raw_document):
    # Compressor returns 5,000 characters.
    assert len(fetch_result["context"]) == 1_200
    context, sources = resources.writer_material(results, max_chars=30_000)
    assert len(resources.context_for("r1", sources[0])) == 3_000
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_tools.py -q
```

Expected: failures show 5 results, 800-character snippets, 2,000-character Researcher context, or 6,000-character stored Writer context.

- [ ] **Step 3: Implement the minimal payload limits**

In `tools.py`, define module constants and apply them at the boundary:

```python
SEARCH_RESULT_LIMIT = 3
SEARCH_SNIPPET_CHARS = 300
RESEARCHER_CONTEXT_CHARS = 1_200
WRITER_SOURCE_CHARS = 3_000
```

Limit search items before returning them, truncate only the model-facing `context`, and retain the Writer copy at `WRITER_SOURCE_CHARS`. Keep URL, title, fetched time, and publication time fields.

- [ ] **Step 4: Write failing Researcher tool-policy tests**

Add to `test_researcher.py`:

```python
def test_model_never_receives_raw_search_web_tool():
    # Run one normal decision and inspect ScriptedModel.bound_tool_names.
    assert "search_web" not in model.bound_tool_names[0]
    assert "research_topic" in model.bound_tool_names[0]

def test_only_first_valid_research_tool_executes_per_decision():
    # Scripted response requests three research_topic calls.
    assert tools.executed_queries == ["first"]
    assert any(e.event_type == "tool.batch_limited" for e in runtime.events)
```

- [ ] **Step 5: Run the Researcher tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_researcher.py -q
```

Expected: `search_web` is still bound and all three calls execute.

- [ ] **Step 6: Implement the constrained Researcher protocol**

Create a model-facing tool list without `search_web`. In each normal round:

```python
finish_calls = [call for call in calls if call["name"] == "finish_research"]
research_calls = [call for call in calls if call["name"] in allowed_research_names]
if finish_calls and research_calls:
    # Invalid mixed action: execute nothing and consume only this decision.
elif len(research_calls) > 1:
    runtime.emit("tool.batch_limited", ..., requested=len(research_calls), executed=1)
    research_calls = research_calls[:1]
```

Execute the selected call through the existing timeout/event path. Preserve early valid finish and finish-only final binding.

- [ ] **Step 7: Run all Task 1 tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_researcher.py tests/multi_agent/test_tools.py tests/multi_agent/test_resources.py -q
```

Expected: all pass, including single-flight, actual network accounting, closeout visibility, and Writer source/context matching.

### Task 2: Make Supervisor retries diagnosable and fallback gaps truthful

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/supervisor.py`
- Modify: `backend/src/deeptrace/multi_agent/prompts.py`
- Test: `backend/tests/multi_agent/test_supervisor.py`

**Interfaces:**
- Consumes: `Supervisor.decide(question, history, remaining_slots, can_dispatch)`.
- Produces: `supervisor.retry` with sanitized `reason_code`; never includes raw Provider errors or response content.
- Produces: a failed review fallback whose gaps are the de-duplicated concrete gaps already present in Researcher results.

- [ ] **Step 1: Write failing retry classification tests**

Add parameterized tests with literal expectations:

```python
@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (AIMessage(content="plain"), "missing_tool_call"),
        (two_decision_calls(), "multiple_tool_calls"),
        (invalid_args_call(), "invalid_arguments"),
    ],
)
def test_supervisor_retry_has_sanitized_reason_code(response, reason):
    assert retry.details["reason_code"] == reason
```

Add separate cases for `dispatch_not_allowed`, `invalid_parent`, `batch_too_large`, and a model timeout returning `provider_timeout`.

- [ ] **Step 2: Run Supervisor tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_supervisor.py -q
```

Expected: retry details currently contain no reason code.

- [ ] **Step 3: Implement a local decision error type and classifier**

In `supervisor.py` add:

```python
class DecisionError(ValueError):
    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)
```

Raise it at each local validation boundary. Catch `TimeoutError` separately as `provider_timeout`; convert Pydantic validation failures to `invalid_arguments`; sanitize all unexpected Provider failures as `provider_failure`. Emit only the code.

- [ ] **Step 4: Write the failing existing-gap fallback test**

Construct a history with one partial and one blocked result, including one duplicate gap. Make both Supervisor responses invalid and assert:

```python
assert decision.action == "finish"
assert not decision.sufficient
assert decision.gaps == ["技术发布日期未确认", "政策原文未取得"]
```

- [ ] **Step 5: Run the fallback test and verify RED**

Expected: current fallback returns only `Supervisor 未返回有效的最终评估`.

- [ ] **Step 6: Implement truthful fallback aggregation**

Read `history[*]["result"]["gaps"]`, preserve first occurrence order, cap to the schema's six gaps, and use the generic Supervisor failure only if no concrete gap exists. If history is empty, return `Supervisor 无法形成有效的初始研究分工`.

- [ ] **Step 7: Tighten Supervisor and Researcher quality prompts**

Update `prompts.py` without exposing private reasoning:

- one bounded topic per assignment;
- at most three required outputs;
- primary sources before aggregators;
- requested years are hard event scope;
- outside-range material can only be background;
- missing primary support becomes a gap rather than a fabricated completion.

Do not add a test that greps prompt text. Exercise the behavior through scripted valid/invalid decisions and the real schema boundaries.

- [ ] **Step 8: Run Supervisor/model tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_supervisor.py tests/multi_agent/test_models.py -q
```

Expected: all pass.

### Task 3: Correct queue/start semantics and faster default scheduling

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/agent.py`
- Modify: `backend/src/deeptrace/config/settings.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/multi_agent/test_agent.py`
- Test: `backend/tests/multi_agent/test_multi_agent_settings.py`

**Interfaces:**
- Consumes: `SupervisorResearchAgent.arun(question) -> AgentResult`, the existing semaphore and `QuotaManager` leases.
- Produces: `researcher.queued` before waiting, `researcher.started` only inside the acquired semaphore, and `researcher.completed` after lease release.
- Produces defaults `multi_agent_concurrency=3`, `multi_agent_max_researcher_rounds=3`; explicit environment variables retain precedence.

- [ ] **Step 1: Write the failing event-order concurrency test**

Use real `asyncio.Event` barriers rather than sleeps. With concurrency 2 and three assignments:

```python
assert queued_ids == ["r1", "r2", "r3"]
assert set(started_before_release) == {"r1", "r2"}
first_wave_gate.set()
assert started_ids[-1] == "r3"
```

Assert every task has exactly one queued, started, and completed event, including an underfunded task.

- [ ] **Step 2: Run the scheduler test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_agent.py -q
```

Expected: `researcher.queued` is absent and r3 currently receives a premature started event.

- [ ] **Step 3: Move event emission across the semaphore boundary**

Emit queued before `async with semaphore`; emit started as the first statement inside it. Perform the lease-too-small check inside the semaphore so event semantics stay truthful. Keep `CancelledError` propagation and release the lease in `finally` for every path.

- [ ] **Step 4: Write failing default and explicit-override settings tests**

```python
assert Settings.from_env().multi_agent_concurrency == 3
assert Settings.from_env().multi_agent_max_researcher_rounds == 3
```

Then set both environment variables to `2` and assert both parsed values are 2.

- [ ] **Step 5: Run settings tests and verify RED**

Expected: defaults are currently concurrency 2 and rounds 4.

- [ ] **Step 6: Update settings and example environment**

Change only Multi-Agent defaults. Preserve validation that concurrency cannot exceed batch size and Supervisor rounds must be at least 2. Do not edit the user's real `.env`.

- [ ] **Step 7: Run Task 3 tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/multi_agent/test_agent.py tests/multi_agent/test_multi_agent_settings.py -q
```

Expected: all pass with deterministic event ordering.

### Task 4: Writer boundary, documentation, regression, and restart

**Files:**
- Modify: `backend/src/deeptrace/multi_agent/agent.py`
- Modify: `backend/src/deeptrace/prompts/writer.py`
- Modify: `backend/src/deeptrace/static/index.html`
- Modify: `backend/README.md`
- Modify: `README.md`
- Modify: `docs/2026-09-06-supervisor-multi-agent-verification.md`
- Test: `backend/tests/multi_agent/test_agent.py`
- Test: `backend/tests/multi_agent/test_entrypoints.py`
- Test: existing Writer renderer/prompt tests

**Interfaces:**
- Consumes: `SharedResearchResources.writer_material(results, max_chars=30_000)` and shared `WriterAgent`.
- Produces: a 30,000-character Multi-Agent Writer ceiling while leaving Basic/Deep Writer construction unchanged.
- Produces: frontend major-event visibility for queued, started, batch-limited, completed, Supervisor retry/review, research/writing completion.

- [ ] **Step 1: Write the failing Writer handoff limit test**

Use a capturing real Writer boundary/fake Provider and assert `SupervisorResearchAgent` requests `writer_material(..., max_chars=30_000)`. Assert returned sources all occur in the bounded context.

- [ ] **Step 2: Run the focused agent test and verify RED**

Expected: agent currently passes `max_chars=50_000`.

- [ ] **Step 3: Apply the Multi-Agent Writer limit and time-scope instruction**

Change the Multi-Agent handoff to 30,000 characters. In the shared Writer prompt, add a mode-neutral rule that facts outside an explicit user time range may appear only as clearly labelled background, never as in-range events. Do not alter citation rendering.

- [ ] **Step 4: Update frontend event visibility and documentation**

Add `researcher.queued` and `tool.batch_limited` to the frontend's major event set. Document the two-research-turn protocol, payload limits, new defaults, retry reason codes, and the fact that a slower/less reliable tool-calling model can still dominate latency.

- [ ] **Step 5: Run all automated verification**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src\deeptrace tests
uvx ruff check src/deeptrace/multi_agent tests/multi_agent src/deeptrace/config/settings.py src/deeptrace/prompts/writer.py tests/test_module_layout.py tests/test_cli.py
uv lock --check
git diff --check
```

Expected: all tests and checks pass. Existing Basic and Deep tests remain green.

- [ ] **Step 6: Review the implementation against the failed run**

Verify statically and with scripted tests that the former pattern cannot recur:

- one Researcher decision cannot execute three search calls;
- `search_web` is not model-visible;
- six 800-character snippets cannot enter one tool observation;
- r3 cannot emit started while waiting behind a concurrency-2 semaphore;
- a failed Supervisor review cannot erase concrete Researcher gaps.

- [ ] **Step 7: Update verification record**

Record test count and commands. State that run `7867aea35c1e` was the diagnostic baseline: 499.9 seconds, 78,259 Token, 19 searches, 8 fetch attempts, 6 successful pages, and two Supervisor repairs. Do not claim a real-world percentage improvement before a paid comparison run exists.

- [ ] **Step 8: Restart the local backend and verify loaded configuration**

Stop only the verified `python -m deeptrace.api` process bound to `127.0.0.1:8000`, start the current virtual-environment Python with a hidden window, and poll `/openapi.json`. Verify the mode enum remains `basic,deep,multi_agent` and construct/close the Multi-Agent agent without issuing a research request.

- [ ] **Step 9: Commit only reviewed implementation files**

Because the worktree contains the user's earlier directory restructure, inspect staged paths before committing. Do not stage unrelated deletions, reports, `.env`, logs, or user files. If a shared dirty file contains inseparable pre-existing changes, leave the implementation uncommitted and report the exact reason rather than absorbing unrelated work.

## Plan Self-Review

- Spec coverage: Researcher policy/payloads map to Task 1; Supervisor reliability and source/time task shaping map to Task 2; concurrency/events/defaults map to Task 3; Writer/frontend/docs/full verification map to Task 4.
- Type consistency: existing public signatures remain unchanged; the only new public model-facing constant is `RESEARCHER_MODEL_TOOLS`; all new events use the existing `RunEvent` details dictionary.
- Scope: role-specific model routing and paid benchmarking remain explicitly outside this plan.
- Test quality: concurrency uses barriers, expectations are literal, external Provider/search/fetch layers remain fakes, and no test merely greps production prompt text.
