# Budget and Tool Ledger Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore exact hierarchical budgets after crashes and make SQL tool-execution followers safe under retries.

**Architecture:** Persist cumulative committed budget units on each tool execution row. Seed the in-memory hierarchical manager exactly once under an asynchronous lock, and keep follower waiting separate from ownership acquisition.

**Tech Stack:** Python 3.11+, asyncio, SQLAlchemy asyncio, Alembic, pytest/pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-09-13-budget-ledger-recovery-design.md`

## Global Constraints

- Only the two approved P1 recovery defects are in scope.
- Published migrations remain immutable; add a new migration.
- Tests precede production changes.

---

### Task 1: Asynchronous Hierarchical Budget Seeding

**Files:**
- Modify: `backend/tests/tools/test_budget.py`
- Create: `backend/tests/application/test_seeded_budgets.py`
- Modify: `backend/src/deeptrace/tools/budget.py`
- Modify: `backend/src/deeptrace/application/assembly.py`

**Interfaces:**
- Produces: `async seed_consumed(consumed: Mapping[BudgetScopeKey, BudgetUnits]) -> None`
- Produces: `_SeededBudgets` initialization that blocks concurrent reserves until one seed attempt completes.

- [x] Write tests proving non-empty seeding updates all three scopes and concurrent reserves invoke the seed once.
- [x] Run the focused tests and verify the current lock misuse and scope-key behavior fail.
- [x] Make seeding asynchronous, add an initialization lock, and build actual agent `BudgetScopeKey` entries.
- [x] Run focused budget tests and verify they pass.

### Task 2: SQL Follower Recovery

**Files:**
- Create: `backend/tests/persistence/test_execution_ledger.py`
- Modify: `backend/src/deeptrace/persistence/execution_ledger.py`

**Interfaces:**
- Preserves: `wait(claim: ExecutionClaim) -> ToolResult`
- Produces: recoverable follower behavior via `ExecutionAbandonedError` and subsequent `claim()` ownership.

- [x] Write a SQL-backed test where an owner records a transient failure while a follower waits.
- [x] Run it and verify the current undefined-variable path fails.
- [x] Keep `wait()` read-only and return a retry signal for recoverable generations.
- [x] Make initial claim/reclaim transitions transactional and safe against uniqueness races.
- [x] Run SQL execution-ledger tests and verify they pass.

### Task 3: Exact Durable Tool Usage

**Files:**
- Modify: `backend/tests/persistence/test_execution_ledger.py`
- Modify: `backend/tests/tools/test_gateway.py`
- Modify: `backend/src/deeptrace/tools/execution_store.py`
- Modify: `backend/src/deeptrace/tools/gateway.py`
- Modify: `backend/src/deeptrace/persistence/execution_ledger.py`
- Modify: `backend/src/deeptrace/persistence/orm.py`
- Create: `backend/alembic/versions/20260913_03_add_tool_budget_usage.py`

**Interfaces:**
- Produces: `complete(claim, result, consumed: BudgetUnits = BudgetUnits()) -> bool`
- Produces: `tool_usage_for_run(run_id) -> dict[tuple[str, str], BudgetUnits]` from stored counters.

- [x] Write tests for transient retries accumulating usage and zero-cost cached/blocked completions.
- [x] Run them and verify status-based inference fails.
- [x] Add cumulative usage columns and migration, then persist supplied committed units on completion.
- [x] Pass exact committed units from the gateway and aggregate the stored counters.
- [x] Run focused tests, the complete non-real suite, migration checks, and the real API smoke test.
