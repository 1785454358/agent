# MySQL Persistence and Distributed Recovery Implementation Plan

> **Status:** Authored 2026-09-13 by the delivery agent (Roadmap Plan 7).

**Goal:** Durable, cross-process recovery: a SQLAlchemy-backed LangGraph checkpointer (asyncmy/MySQL in production, aiosqlite in tests), a SQL tool-execution ledger, and forced-crash recovery tests proving idempotent resume at every key boundary.

**Constraints:**
- Same SQL via SQLAlchemy `AsyncEngine`; tests run on `sqlite+aiosqlite`, production on `mysql+asyncmy`. No runtime branching in graph code.
- At-least-once delivery + checkpointed execution + idempotent side effects; no exactly-once claims.
- Recovery tests cover crashes after planning, tool execution, and memory commit; a completed tool call ID must replay (not re-execute) after resume.

## Tasks

1. **ORM rows + DDL** (`persistence/orm.py`): `CheckpointRow`, `CheckpointWriteRow`, `ToolExecutionRow`, `MemoryRecordRow` (deferred memory row noted below).
2. **SqlAlchemyCheckpointSaver** (`persistence/checkpoint.py`): BaseCheckpointSaver over the harness strict serde; `aget_tuple`/`alist`/`aput`/`aput_writes`/`adelete_thread`.
3. **SqlAlchemyToolExecutionStore** (`persistence/execution_ledger.py`): claim-by-unique-key (owner + status), terminal result JSON, replay on duplicate, reclaim of abandoned claims.
4. **Recovery tests** (`tests/integration/test_recovery.py`): forced crash injection (planning, post-tool, memory commit) against the full runtime graph on aiosqlite; resume re-invokes with `None` input; asserts provider called once, evidence ingested once, outcome correct.
5. Exit gate: full non-real suite + compileall.

**Deliberately deferred:** SQL memory-store + SQL evidence-store adapters (in-memory adapters already implement the exact production semantics; SQL mapping is mechanical), Redis lease/recovery scanner hardening (existing broker covered by current tests).
