# Tool Gateway and Evidence Store Implementation Plan

> **For agentic workers:** Execute task-by-task with strict red-green-refactor. Each task requires a fresh implementation pass, a specification review, and a code-quality review before commit.

**Goal:** Replace strategy-specific tool wrappers with one typed, policy-enforced, replay-safe Tool Gateway and an Evidence Store that keeps large research payloads out of graph state and model context.

**Architecture:** Tool definitions and external capability adapters live behind a runtime `ToolRegistry`. Every invocation enters a single `ToolGateway` pipeline in the approved order: registry, allowlist, validation, security, idempotency, budget reservation, cache/singleflight, events, timeout/attempt, normalization, Evidence ingestion, budget commit, completion event. Serializable request/result contracts cross graph boundaries; clients, locks, futures, schemas, and handlers remain runtime-only. The first implementation uses in-memory ports so Plan 3 can consume it; MySQL durability is added in Plan 7.

**Tech Stack:** Python 3.11+, Pydantic 2, asyncio, hashlib, LangGraph-compatible runtime injection, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md`, especially sections 14.1–14.6.

**Depends on:** `docs/superpowers/plans/2026-09-10-agent-harness-foundation.md`

---

## Scope and invariants

- The only atomic research tool names are `search_web`, `fetch_page`, and `search_memory`.
- `research_topic`, `finish_task`, and `finish_research` are not registered tools. Later plans implement their behavior with LangGraph nodes and routes.
- `ToolRequest` and `ToolResult` are serializable Pydantic contracts. They never contain clients, locks, futures, exception objects, or full page bodies.
- The Gateway accepts canonical `ResearchMode` values through `ToolCaller`. Raw strings and legacy aliases are normalized at application boundaries, never inside the Tool Gateway.
- Validation and policy rejection consume no tool or network budget.
- A cache follower and an idempotent replay consume no network budget.
- A failed real network attempt is recorded and charged according to the reservation policy, but is not added to the success cache.
- Concurrent identical cache misses share one leader operation. Cancellation of a follower must not cancel the leader.
- Large bodies are persisted as `Evidence`; the result returned to the graph/model contains a bounded preview plus `data_ref` and `evidence_ids`.
- Provider exceptions are converted to stable public error codes. Credentials, headers, response bodies, and exception messages are not copied into `ToolResult` or events.
- Retry ownership is singular. This plan performs at most one adapter call per gateway execution; later graph nodes may attach an explicit LangGraph `RetryPolicy` for transient provider failures.
- Existing Deep and Multi-Agent execution paths remain runnable until their replacement strategy subgraphs are delivered. This plan adds the shared gateway but does not delete old wrappers.
- Do not touch or stage `docs/resume/多模式深度研究Agent简历项目材料.md`.

## Target module layout

```text
backend/src/deeptrace/
├── domain/
│   ├── evidence.py
│   └── tools.py
├── tools/
│   ├── contracts.py
│   ├── registry.py
│   ├── policy.py
│   ├── budget.py
│   ├── evidence_store.py
│   ├── execution_store.py
│   ├── cache.py
│   ├── gateway.py
│   └── adapters.py
└── harness/
    ├── checkpoint.py
    └── context.py
```

---

### Task 1: Define serializable tool and Evidence contracts

**Files:**

- Create: `backend/src/deeptrace/domain/tools.py`
- Modify: `backend/src/deeptrace/domain/evidence.py`
- Modify: `backend/src/deeptrace/domain/__init__.py`
- Modify: `backend/src/deeptrace/harness/checkpoint.py`
- Test: `backend/tests/domain/test_tools.py`
- Test: `backend/tests/domain/test_evidence.py`
- Test: `backend/tests/harness/test_state.py`

- [ ] Write failing contract tests first.

Cover:

- `ToolName` has exactly `search_web`, `fetch_page`, and `search_memory`;
- request IDs, run IDs, thread IDs, call IDs, and tool names are required and bounded;
- arguments are JSON-compatible and size-bounded;
- `ToolResult` expresses `ok`, `error_code`, bounded `preview`, optional `data_ref`, unique `evidence_ids`, `cached`, and `replayed` without full content;
- invalid success/error combinations are rejected;
- `Evidence` records canonical URL, title, media type, content hash, fetched/published timestamps, source quality, lifecycle status, version, optional `supersedes`, and bounded metadata;
- full content belongs to the Evidence Store value, not the checkpointed Evidence reference;
- strict checkpoint serialization round-trips the new request/result/reference models and continues to reject unregistered custom models.

- [ ] Run the new tests and confirm RED because the contracts do not exist.
- [ ] Implement the smallest Pydantic models, validators, public exports, and exact serializer allowlist additions.
- [ ] Run focused domain and checkpoint tests.
- [ ] Refactor names and bounds without changing behavior.
- [ ] Specification review, then quality review.
- [ ] Commit: `feat: define tool and evidence contracts`

### Task 2: Add runtime ToolSpec registry and mode/caller allowlists

**Files:**

- Create: `backend/src/deeptrace/tools/contracts.py`
- Create: `backend/src/deeptrace/tools/registry.py`
- Create: `backend/src/deeptrace/tools/policy.py`
- Test: `backend/tests/tools/test_registry.py`
- Test: `backend/tests/tools/test_policy.py`

- [ ] Write failing tests for runtime-only tool definitions.

`ToolSpec` should be an immutable runtime record containing the canonical name, Pydantic argument model, async handler, capability classification, cache policy, timeout, preview limit, and whether successful output becomes Evidence. `ToolRegistry` must reject duplicates and raw-string lookups. It must not be serializable into Harness State.

Allowlist policy must encode these initial permissions:

| Caller | Allowed capability |
|---|---|
| Workflow graph | deterministic graph-selected research tools |
| Plan-and-Execute executor | registered research tools |
| Multi-Agent researcher | registered research tools |
| Multi-Agent supervisor | none |
| Answer / Brief / Report | Evidence reads only, no network tools |
| Memory consolidation | Memory Store only |

Tests must prove that unknown tools and disallowed callers fail before argument validation or handler invocation. Canonical enum enforcement must not be bypassable via `StrEnum == str` equality.

- [ ] Confirm RED.
- [ ] Implement registry plus separate allowlist and URL security policy ports.
- [ ] Use the existing URL normalizer at the fetch boundary; reject unsupported schemes, loopback/private/link-local hosts, embedded credentials, and URLs not established by an approved search/memory result or direct user input.
- [ ] Run focused tests.
- [ ] Specification review, then quality review.
- [ ] Commit: `feat: add tool registry and policies`

### Task 3: Implement hierarchical reservation-based budgets

**Files:**

- Create: `backend/src/deeptrace/tools/budget.py`
- Test: `backend/tests/tools/test_budget.py`

- [ ] Write failing concurrent tests for Run → Mode → Agent budget scopes.

The API must separate `reserve`, `commit`, and `release`. A reservation describes tool calls, network requests, and fetched pages; model/token/round counters may be represented in the snapshot but do not need provider integration in this plan.

Required behavior:

- reservations are atomic under concurrency;
- no child scope can exceed its own ceiling or its ancestors' remaining capacity;
- a rejected reservation changes no counters;
- validation/policy failures never request a reservation;
- cache hits and replay hits release/no-op their provisional network reservation;
- a real attempted network call commits one network unit whether it succeeds or fails;
- unused page capacity is released;
- double commit/release is idempotent;
- snapshots are deterministic and can update `BudgetSnapshot` later without exposing locks in state.

- [ ] Confirm RED.
- [ ] Implement immutable scope keys, reservation records, and an async in-memory manager.
- [ ] Run focused tests including `asyncio.gather` contention.
- [ ] Refactor only after all concurrency tests pass.
- [ ] Specification review, then quality review.
- [ ] Commit: `feat: add hierarchical tool budgets`

### Task 4: Implement Evidence Store and tool execution ledger ports

**Files:**

- Create: `backend/src/deeptrace/tools/evidence_store.py`
- Create: `backend/src/deeptrace/tools/execution_store.py`
- Test: `backend/tests/tools/test_evidence_store.py`
- Test: `backend/tests/tools/test_execution_store.py`

- [ ] Write failing tests for content-addressed Evidence and replay ownership.

Define protocols and concurrency-safe in-memory adapters with the same semantics expected from Plan 7's MySQL implementations:

- Evidence identity derives from normalized source identity plus content hash, not random insertion order;
- identical content upserts to one active record;
- changed content creates a new version with `supersedes` while preserving the older record;
- `get`, `get_many`, and body reads preserve request order and tenant boundaries;
- execution ledger keys include tenant/run/call identity plus a canonical request fingerprint;
- first claimant owns execution, concurrent followers wait through a cancellation-shielded completion handle, and later duplicates replay the terminal result;
- a call ID reused with a different fingerprint is a conflict, never an accidental replay;
- cancelled or abandoned ownership can be reclaimed explicitly; ordinary provider failure is terminal for that call ID and is replayed rather than re-executed.

Locks/futures may exist only inside the in-memory adapters and never cross the contract boundary.

- [ ] Confirm RED.
- [ ] Implement protocols, canonical hashing helpers, and in-memory adapters.
- [ ] Run focused tests including concurrent claim and tenant isolation.
- [ ] Specification review, then quality review.
- [ ] Commit: `feat: add evidence and execution stores`

### Task 5: Add success cache and cancellation-safe singleflight

**Files:**

- Create: `backend/src/deeptrace/tools/cache.py`
- Test: `backend/tests/tools/test_cache.py`

- [ ] Write failing tests for normalized cache keys and concurrent ownership.

Required behavior:

- search keys use normalized query, provider identity, and sorted options;
- page keys use normalized URL plus content-version/refresh semantics;
- only successful normalized results enter the cache;
- an identical concurrent miss invokes its factory once;
- followers receive `cached=True`; the leader receives `cached=False`;
- cancelling one follower does not cancel the shared leader;
- leader cancellation/failure wakes followers with a sanitized outcome and removes the flight so a later new call may retry;
- refresh bypasses the ordinary page cache without corrupting the prior entry until a new success is available.

- [ ] Confirm RED.
- [ ] Implement an in-memory cache port and singleflight coordinator.
- [ ] Run focused cancellation and failure tests.
- [ ] Specification review, then quality review.
- [ ] Commit: `feat: add tool cache and singleflight`

### Task 6: Build the ordered Tool Gateway pipeline

**Files:**

- Create: `backend/src/deeptrace/tools/gateway.py`
- Modify: `backend/src/deeptrace/harness/context.py`
- Test: `backend/tests/tools/test_gateway.py`

- [ ] Write failing integration tests with scripted handlers and recording middleware dependencies.

The test suite must prove this exact externally observable ordering:

```text
registry → allowlist → validation → security → idempotency
→ budget reservation → cache/singleflight → start event
→ adapter timeout/call → normalization → Evidence ingestion
→ budget commit/release → completion event → ledger completion
```

Required scenarios:

- unknown/disallowed/invalid/insecure requests never reserve budget and never emit a start event;
- replay returns the prior terminal `ToolResult` with `replayed=True` and no budget or adapter call;
- cache hit returns `cached=True`, makes no adapter call, and consumes no network unit;
- concurrent identical requests with different call IDs share the provider operation while producing separate ledger completions;
- a successful small result stays inline as a bounded preview;
- a successful large/page result persists Evidence and returns only preview + `data_ref` + Evidence ID;
- handler exceptions and timeouts are sanitized, recorded, charged as real attempts, and emit a completion event;
- events contain IDs, canonical tool/mode, cache/replay flags, duration, budget deltas, and stable error code, but no raw body or secret-bearing exception text;
- cancellation propagates without writing a false success and leaves ledger ownership recoverable according to Task 4 semantics.

Update `HarnessContext` protocols to use typed `ToolRequest`, `ToolResult`, and Evidence references while keeping runtime implementations out of graph state.

- [ ] Confirm RED.
- [ ] Implement the gateway as a small orchestrator over the tested ports. Do not introduce LangGraph nodes here; graph integration begins in Plan 3.
- [ ] Run focused gateway, harness, and strict-serializer tests.
- [ ] Specification review, then quality review.
- [ ] Commit: `feat: implement unified tool gateway`

### Task 7: Register the three atomic research adapters and lock the public contract

**Files:**

- Create: `backend/src/deeptrace/tools/adapters.py`
- Modify: `backend/src/deeptrace/tools/__init__.py`
- Modify: `backend/tests/test_module_layout.py`
- Create: `backend/tests/tools/test_adapters.py`
- Create: `backend/tests/tools/test_gateway_exit_gate.py`

- [ ] Write failing adapter and exit-gate tests.

Adapters wrap the existing search function, scraper/fetcher, and page-memory lookup without embedding orchestration policy. They return a normalized internal payload accepted by the gateway. They do not maintain their own budget, idempotency, cache, or singleflight state.

Exit-gate test setup:

- register only `search_web`, `fetch_page`, and `search_memory`;
- use two Researcher callers plus one forbidden Supervisor caller;
- run concurrent identical searches and fetches;
- validate an intentionally malformed request;
- repeat one call ID after completion;
- return a body over the offload threshold.

Assertions:

- the Supervisor is rejected by policy;
- malformed input consumes zero budget;
- concurrent calls invoke each external provider once;
- only leaders consume network budget;
- replay does not invoke the provider;
- large output is retrievable from Evidence Store and absent from `ToolResult.preview` beyond its configured bound;
- public imports expose stable contracts and builders without exposing old `ResearchToolbox` or `ResearcherTools` as the new API;
- legacy Deep/Multi-Agent focused tests still pass unchanged.

- [ ] Confirm RED.
- [ ] Implement adapters and explicit exports.
- [ ] Run focused new and legacy tool tests.
- [ ] Run `uv run pytest -m "not real"`.
- [ ] Run `uv run python -m compileall -q src tests`.
- [ ] Review the complete Plan 2 diff for leaked secrets, unbounded payloads, duplicate retry layers, and state serialization violations.
- [ ] Specification review, then quality review.
- [ ] Commit: `test: lock tool gateway exit gate`

---

## Plan 2 exit gate

Before starting Plan 3, all of the following must be true:

- [ ] All new Tool Gateway contracts are strict-checkpoint serializable.
- [ ] The runtime registry contains exactly the three atomic tools.
- [ ] Mode/caller allowlists prevent Supervisor and response graphs from using network tools.
- [ ] Invalid and policy-rejected requests consume no budget.
- [ ] Concurrent identical work is singleflight and only the leader consumes network budget.
- [ ] Completed call IDs replay safely and conflicting reuse is rejected.
- [ ] Large results live in Evidence Store and graph/model-facing results contain bounded previews and references only.
- [ ] Provider failures and events are sanitized.
- [ ] Old production paths still pass their focused tests.
- [ ] The full non-real suite and compile check pass.
- [ ] The pre-existing resume document modification remains untouched and uncommitted.

## Deferred deliberately

- `ResearchTopicGraph` orchestration: Plan 3 for Workflow, then reused by later strategy subgraphs.
- Production MySQL Evidence and execution-ledger adapters: Plan 7.
- Redis cross-process singleflight/leases: Plan 7; this plan defines semantics with in-memory adapters.
- Automatic long-term memory recall and consolidation: Plan 6.
- Model/tool retry policies wired to graph nodes: the owning strategy-subgraph plans.
- Removal of `deep.tools.ResearchToolbox`, `multi_agent.tools.ResearcherTools`, and `multi_agent.resources.SharedResearchResources`: Plans 4–5 after their consumers migrate.
