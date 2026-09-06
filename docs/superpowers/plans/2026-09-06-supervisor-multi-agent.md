# Supervisor Multi-Agent Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `multi_agent` research mode whose Supervisor dispatches bounded independent ReAct Researchers, reviews their results, and writes one source-grounded report without changing Basic or Deep execution.

**Architecture:** `deeptrace/multi_agent/` is a peer of `basic/` and `deep/`. One run owns shared search/fetch/cache/quota resources; each Researcher owns its conversation, source view, and local quota. The Supervisor plans and reviews batches, while the existing shared Writer receives selected original page context.

**Tech Stack:** Python 3.11, asyncio, Pydantic v2, LangChain messages/tool binding, Tavily, existing scraper/BGE/Writer, FastAPI/SSE, pytest.

**Spec:** `docs/superpowers/specs/2026-09-06-supervisor-multi-agent-design.md`

## Global Constraints

- Preserve the current `basic` and `deep` implementations; do not import their flow code from `multi_agent`.
- Time, Token, and estimated cost are observational only.
- Bound work using Supervisor rounds, Researcher rounds/count, concurrency, and actual network tool attempts.
- Do not introduce ResearchNote, Claim, Evidence, Verifier, or per-page LLM compression.
- Writer facts come from selected original page context; task summaries coordinate work only.
- Keep numbered headings, first-use numeric citations, and URLs at the report end through the shared Writer.
- Use the user's current `basic/`, `deep/`, `writer/`, `models/`, and `observability/` layout as the baseline.

---

### Task 1: Typed contracts, settings, and usage accounting

**Files:**
- Create: `backend/src/deeptrace/multi_agent/__init__.py`
- Create: `backend/src/deeptrace/multi_agent/models.py`
- Modify: `backend/src/deeptrace/config/settings.py`
- Modify: `backend/src/deeptrace/models/metrics.py`
- Modify: `backend/src/deeptrace/observability/token_metrics.py`
- Test: `backend/tests/multi_agent/test_models.py`
- Test: `backend/tests/config/test_settings.py`

**Interfaces:**
- Produces `ResearchAssignment`, `ResearcherResult`, `SupervisorDecision`, and native tool schemas.
- Produces settings named `multi_agent_max_researchers`, `multi_agent_max_batch_size`, `multi_agent_concurrency`, `multi_agent_max_supervisor_rounds`, `multi_agent_max_researcher_rounds`, `multi_agent_max_tool_calls`, `multi_agent_max_tools_per_researcher`, `multi_agent_call_timeout_seconds`, `multi_agent_memory_max_age_days`, and `multi_agent_memory_path`.
- Extends `UsageBreakdown` with default-zero `supervisor` and `researcher` fields included exactly once in `total`.

- [ ] Write tests that reject invalid dispatches, invalid parent IDs, empty concrete gaps, and invalid settings/path collisions.
- [ ] Run the focused tests and verify imports or assertions fail because the new contracts/settings do not exist.
- [ ] Implement the minimal Pydantic contracts and bounded settings; preserve deserialization of old usage payloads through default fields.
- [ ] Run focused tests and existing config/model tests until green.
- [ ] Commit only this task's files.

Representative behavioral assertion:

```python
def test_usage_total_includes_multi_agent_roles_once():
    usage = UsageBreakdown(
        supervisor=TokenUsage(total_tokens=2),
        researcher=TokenUsage(total_tokens=3),
    )
    assert usage.total.total_tokens == 5
```

### Task 2: Atomic quota leases and shared single-flight resources

**Files:**
- Create: `backend/src/deeptrace/multi_agent/runtime.py`
- Create: `backend/src/deeptrace/multi_agent/resources.py`
- Test: `backend/tests/multi_agent/test_runtime.py`
- Test: `backend/tests/multi_agent/test_resources.py`

**Interfaces:**
- `MultiAgentRuntime.invoke(model, messages, role)` records steps, role usage, duration, and per-run events.
- `QuotaManager.allocate_initial(task_ids) -> dict[str, ToolLease]` reserves 20% and divides the first-pass pool deterministically.
- `QuotaManager.allocate_follow_up(task_ids) -> dict[str, ToolLease]` uses returned capacity and the reserve without exceeding global/local bounds.
- `ToolLease.acquire_network() -> bool` atomically consumes one actual search/fetch attempt.
- `SharedResearchResources.search(query, lease)` and `.fetch(url, lease, refresh=False)` single-flight identical requests and return cache metadata.

- [ ] Write an async test where three first-pass leases receive fair capacity and the first lease cannot consume another task's reservation.
- [ ] Verify the test fails because quota classes are missing.
- [ ] Implement allocation, return of unused capacity, atomic acquisition, and run-level usage/events.
- [ ] Write barrier-driven tests proving identical concurrent query/URL operations call the external dependency once and only the leader is charged.
- [ ] Verify RED, implement single-flight search/fetch and task-local read registration, then verify GREEN.
- [ ] Commit only runtime/resource files and their tests.

Representative allocation assertion:

```python
async def test_first_batch_reserves_follow_up_capacity():
    quota = QuotaManager(total=30, per_researcher=10, reserve_ratio=0.2)
    leases = await quota.allocate_initial(["r1", "r2", "r3"])
    assert [leases[key].limit for key in ("r1", "r2", "r3")] == [8, 8, 8]
    assert quota.reserved == 6
```

### Task 3: Task-local research tools

**Files:**
- Create: `backend/src/deeptrace/multi_agent/tools.py`
- Test: `backend/tests/multi_agent/test_tools.py`

**Interfaces:**
- `ResearcherTools.execute(name, args) -> dict` validates `research_topic`, `search_web`, `fetch_page`, and `search_memory` arguments.
- Each tool view owns `assignment`, `known_urls`, `read_sources`, `queries`, and its `ToolLease`.
- The run resource owner keeps canonical documents and context; `.writer_context(results)` returns fair, de-duplicated original context and matching URLs.

- [ ] Write tests showing search snippets do not count as read sources, cached pages can be read by another task without another network charge, and an unknown URL is rejected.
- [ ] Verify RED because `ResearcherTools` is missing.
- [ ] Implement task views over shared resources, `research_topic` search-and-fetch composition, memory lookup, and BGE ingestion.
- [ ] Add tests for combination-tool accounting, failed attempts, task-specific context selection, and Writer source/context matching.
- [ ] Run focused tests and commit this vertical tool slice.

### Task 4: Supervisor and independent ReAct Researcher

**Files:**
- Create: `backend/src/deeptrace/multi_agent/prompts.py`
- Create: `backend/src/deeptrace/multi_agent/supervisor.py`
- Create: `backend/src/deeptrace/multi_agent/researcher.py`
- Test: `backend/tests/multi_agent/test_supervisor.py`
- Test: `backend/tests/multi_agent/test_researcher.py`

**Interfaces:**
- `Supervisor.decide(question, history, *, remaining_slots, can_dispatch) -> SupervisorDecision` uses ordinary tool binding and at most one repair call.
- `Researcher.run(assignment, tools) -> ResearcherResult` reserves its final configured decision for finish-only closeout.
- Both invoke through `MultiAgentRuntime`; neither sets forced `tool_choice`.

- [ ] Write Supervisor tests for a valid initial batch, invalid-output repair, parent validation, final-round finish-only behavior, and failure fallback.
- [ ] Verify RED, implement the Supervisor, and verify GREEN.
- [ ] Write Researcher tests proving early completion does not add another call, last tool observations reach closeout, zero remaining network quota still permits closeout, malformed closeout is conservative, and histories are task-local.
- [ ] Verify RED, implement the Researcher loop, and verify GREEN.
- [ ] Commit the role implementation and tests.

### Task 5: Batch scheduler, result synthesis, and lifecycle

**Files:**
- Create: `backend/src/deeptrace/multi_agent/agent.py`
- Test: `backend/tests/multi_agent/test_agent.py`

**Interfaces:**
- `SupervisorResearchAgent.arun(question) -> AgentResult` coordinates bounded batches and adapts to the shared public result.
- A semaphore limits active Researchers; all valid tasks in the batch either execute or yield an explicit result.
- `aclose()` closes shared external resources once.

- [ ] Write an integration-style scripted test where r1 exhausts its lease while r2/r3 still execute and the Supervisor receives all three results.
- [ ] Verify RED because the scheduler does not exist.
- [ ] Implement stable task ID assignment, batch validation, fair lease allocation, `asyncio.gather` isolation, review/dispatch loop, and Writer handoff.
- [ ] Add tests for one Researcher failure isolation, no dispatch without a future review round, total Researcher cap, specific unresolved gaps, cancellation propagation, and Writer fallback status.
- [ ] Run the complete `tests/multi_agent` suite and commit the scheduler slice.

### Task 6: Dependency assembly and product entry points

**Files:**
- Create: `backend/src/deeptrace/multi_agent/service.py`
- Modify: `backend/src/deeptrace/multi_agent/__init__.py`
- Modify: `backend/src/deeptrace/__init__.py`
- Modify: `backend/src/deeptrace/api.py`
- Modify: `backend/src/deeptrace/cli.py`
- Modify: `backend/src/deeptrace/static/index.html`
- Modify: `backend/.env.example`
- Modify: `backend/README.md`
- Modify: `docs/README.md`
- Test: `backend/tests/multi_agent/test_service.py`
- Test: `backend/tests/api/test_api.py`
- Test: `backend/tests/test_cli.py`
- Test: `backend/tests/test_module_layout.py`

**Interfaces:**
- `build_multi_agent(settings, on_event=None) -> SupervisorResearchAgent` owns shared provider/search/fetch/BGE/memory dependencies.
- `build_real_agent(..., mode="multi_agent")` routes only that exact value to the new builder and rejects unknown values.
- API records and CLI accept `basic`, `deep`, `multi_agent`; default remains `basic`.

- [ ] Write route/API/CLI tests and verify they fail on the absent third mode.
- [ ] Implement dependency assembly, route changes, type literals, select option, and role-aware major events.
- [ ] Add settings documentation without secrets and describe the new architecture/limits accurately.
- [ ] Run focused entry-point tests and commit only touched public files plus the new service.

### Task 7: Regression, quality review, and finite real validation

**Files:**
- Modify only files required to address verified failures.
- Create: `docs/2026-09-06-supervisor-multi-agent-verification.md`

**Interfaces:**
- Consumes the completed mode and records reproducible verification without treating benchmark outcomes as hard-coded behavior.

- [ ] Run `python -m pytest -q` from `backend` and confirm all Basic, Deep, and Multi-Agent tests pass.
- [ ] Run Ruff (or the repository's configured equivalent), compile/import checks, and inspect staged diffs for secrets and unrelated changes.
- [ ] Review correctness, readability, architecture, security, and performance; fix required findings with a failing regression test first.
- [ ] Start the app only after automated checks pass and verify all three frontend modes can create a run and stream events.
- [ ] If real credentials are configured, run one finite Multi-Agent research question and record task coverage, duplicate queries, network attempts, Token, duration, and report limitations; do not expose credentials or provider exception bodies.
- [ ] Commit verification documentation and any regression-tested fixes.

## Plan self-review

- Every spec section maps to a task: contracts/config (1), concurrency/quota/cache (2), tools/original context/memory (3), roles/closeout (4), orchestration/error handling/Writer (5), entry points/UI/docs (6), verification (7).
- Signatures and names are consistent across producer/consumer tasks.
- Existing user restructuring is the baseline, and no task requires restoring deleted legacy modules.
- No implementation step relies on a new third-party dependency.
- No task measures success by changing a status label alone.
