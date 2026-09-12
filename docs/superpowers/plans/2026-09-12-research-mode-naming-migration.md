# Research Mode Naming Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the obsolete Profile vocabulary in the new Harness foundation and Tool Gateway modules with the approved Mode and Strategy vocabulary before more runtime components depend on it.

**Architecture:** Perform one atomic contract migration across domain models, graph state, strategy registration, routing, tool policy, and hierarchical budgets. Legacy API values `basic` and `deep` remain accepted only by the application-boundary normalizer; no Python compatibility aliases for old Profile type or field names remain.

**Tech Stack:** Python 3.11+, Pydantic 2, LangGraph 1.x, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md`

## Global Constraints

- The public and domain selection concept is `ResearchMode` with `workflow`, `plan_execute`, and `multi_agent` values.
- Strategy implementations satisfy `ResearchStrategyGraph` and are resolved through `StrategyRegistry`.
- Answer, Brief, and Report use `ResponseMode`.
- State fields are `active_mode`, `selected_mode`, and `response_mode`.
- `ResearchOutcome` stores `mode`.
- The top-level graph builder is `build_agent_runtime_graph`; the name must not imply that the Harness is one graph.
- Tool caller and budget fields use `mode`; budget construction uses `for_mode`.
- `ConversationIntent.SWITCH_MODE` has value `switch_mode`.
- Do not keep `ResearchProfile`, `ResponseProfile`, `ProfileRegistry`, `ProfileRegistration`, old Profile state fields, or old normalization function aliases.
- The migration changes names only. Routing, serialization, policies, budget accounting, concurrency, and persistence behavior remain unchanged.

---

### Task 1: Migrate Harness and Tool Gateway contracts to Mode and Strategy names

**Files:**
- Modify: `backend/tests/domain/test_execution.py`
- Modify: `backend/tests/domain/test_conversation.py`
- Modify: `backend/tests/harness/test_state.py`
- Modify: `backend/tests/harness/test_registry.py`
- Modify: `backend/tests/harness/test_graph.py`
- Modify: `backend/tests/harness/test_public_contracts.py`
- Modify: `backend/tests/tools/test_policy.py`
- Modify: `backend/tests/tools/test_budget.py`
- Modify: `backend/tests/test_module_layout.py`
- Modify: `backend/src/deeptrace/domain/execution.py`
- Modify: `backend/src/deeptrace/domain/__init__.py`
- Modify: `backend/src/deeptrace/harness/state.py`
- Modify: `backend/src/deeptrace/harness/checkpoint.py`
- Modify: `backend/src/deeptrace/harness/registry.py`
- Modify: `backend/src/deeptrace/harness/graph.py`
- Modify: `backend/src/deeptrace/harness/__init__.py`
- Modify: `backend/src/deeptrace/tools/policy.py`
- Modify: `backend/src/deeptrace/tools/budget.py`

**Interfaces:**
- Consumes: existing behavior of domain execution models, top-level LangGraph routing, caller policy, strict checkpoint serialization, and hierarchical budgets
- Produces: `ResearchMode`, `ResponseMode`, `normalize_research_mode`, `StrategyRegistration`, `StrategyRegistry`, `build_agent_runtime_graph`, mode-named State fields, mode-named caller policy, and mode-named budget scopes

- [ ] **Step 1: Rewrite public-contract tests to the desired API**

Change imports and assertions so the expected API is equivalent to:

```python
from deeptrace.domain import ResearchMode, ResponseMode, normalize_research_mode
from deeptrace.harness import StrategyRegistry, build_agent_runtime_graph

assert ResearchMode.WORKFLOW.value == "workflow"
assert ResponseMode.REPORT.value == "report"
assert normalize_research_mode("basic") is ResearchMode.WORKFLOW
assert StrategyRegistry.__name__ == "StrategyRegistry"
assert callable(build_agent_runtime_graph)
```

Update State, routing, policy, and budget tests to use `active_mode`, `selected_mode`, `response_mode`, `ResearchOutcome.mode`, `CallerIdentity.mode`, `CallerIdentity.response_mode`, `BudgetScopeKey.mode`, and `BudgetScopeKey.for_mode`.

- [ ] **Step 2: Run the migrated tests and verify RED**

Run:

```powershell
uv run pytest tests/domain/test_execution.py tests/domain/test_conversation.py tests/harness tests/tools/test_policy.py tests/tools/test_budget.py tests/test_module_layout.py -q
```

Expected: collection fails because `ResearchMode`, `ResponseMode`, `StrategyRegistry`, and `build_agent_runtime_graph` do not exist. This proves the tests target the new public contract.

- [ ] **Step 3: Rename domain types and serializable fields**

Implement these exact declarations and propagate them through exports and strict checkpoint registration:

```python
class ResearchMode(StrEnum):
    WORKFLOW = "workflow"
    PLAN_EXECUTE = "plan_execute"
    MULTI_AGENT = "multi_agent"

class ResponseMode(StrEnum):
    ANSWER = "answer"
    BRIEF = "brief"
    REPORT = "report"

def normalize_research_mode(value: str | ResearchMode) -> ResearchMode: ...
```

Rename `ConversationIntent.SWITCH_PROFILE` to `SWITCH_MODE` with value `switch_mode`. Rename the `ResearchOutcome` field to `mode`. Rename conversation and turn State fields to `active_mode`, `selected_mode`, and `response_mode` without adding fallback reads for old keys.

- [ ] **Step 4: Rename registration and graph routing contracts**

Rename `ProfileRegistration` to `StrategyRegistration` and `ProfileRegistry` to `StrategyRegistry`. The registry stores `ResearchMode` keys and exposes `modes()`. Rename graph helpers from profile to mode or strategy vocabulary and expose:

```python
def build_agent_runtime_graph(
    registry: StrategyRegistry,
    checkpointer=None,
): ...
```

The routed strategy must return a `ResearchOutcome` whose `mode` equals the selected `ResearchMode`; mismatches raise an explicit error.

- [ ] **Step 5: Rename tool policy and budget scope contracts**

Use `mode` and `response_mode` in `CallerIdentity`, `_ROLE_MODES`, validation messages, and authorization logic. Use `mode` and `for_mode` in `BudgetScopeKey`, lineage construction, paths, and deterministic snapshot ordering. Keep all limits and locking behavior unchanged.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
uv run pytest tests/domain/test_execution.py tests/domain/test_conversation.py tests/harness tests/tools/test_policy.py tests/tools/test_budget.py tests/test_module_layout.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Prove old production vocabulary is gone**

Run:

```powershell
$legacy = rg -n "ResearchProfile|ResponseProfile|ProfileRegistry|ProfileRegistration|active_profile|selected_profile|response_profile|for_profile|SWITCH_PROFILE|normalize_research_profile|build_harness_graph" src/deeptrace tests --glob "*.py"
if ($LASTEXITCODE -eq 0) { $legacy; throw "Legacy Profile vocabulary remains" }
```

Expected: no matches in production code or tests.

- [ ] **Step 8: Run regression and compile checks**

Run:

```powershell
uv run pytest -m "not real" -q
uv run python -m compileall -q src tests
```

Expected: the non-real suite and compile check pass.

- [ ] **Step 9: Review and commit**

Review correctness, public naming, serializer registration, graph routing, policy enforcement, concurrency behavior, and accidental compatibility aliases. Then run:

```powershell
git add -- backend/src/deeptrace backend/tests
git diff --cached --check
git commit -m "refactor: rename research profiles to modes"
```

Expected: only the planned source and test files are committed.
