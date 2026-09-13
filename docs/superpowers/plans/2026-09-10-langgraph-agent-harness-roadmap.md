# LangGraph Agent Harness Delivery Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each linked plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved ResearchPilot Agent Harness design through independently reviewable, testable vertical slices.

**Architecture:** A LangGraph top-level runtime graph owns the shared conversation lifecycle and invokes registered research, response, and memory subgraphs through typed contracts. MySQL-backed checkpoints and stores, an idempotent Tool Gateway, and isolated strategy state are introduced incrementally while the existing application remains runnable until final cutover.

**Tech Stack:** Python 3.11+, Pydantic 2, LangGraph 1.x, LangChain OpenAI adapters, FastAPI, MySQL, Redis Streams, SQLAlchemy asyncio, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md`

> **Delivery status (2026-09-13, after external audit fixes):** Plans 1–8 delivered and
> the cutover is closed: API / Worker / CLI all run through the top-level runtime graph,
> the legacy Basic/Deep/Multi-Agent orchestration modules are deleted, MySQL migrations
> exist for the checkpoint/ledger/memory tables, the API accepts `thread_id` for
> multi-turn, dynamic compression and memory injection are implemented, and transient
> tool errors retry at node level. Plan docs: `2026-09-13-{plan-execute-strategy,
> multi-agent-strategy,mysql-distributed-recovery}.md`; decisions in
> `2026-09-13-harness-implementation-decisions.md`. Baseline: 364 non-real tests green
> (legacy suites removed with their modules) + real-API smoke test (`-m real`) passing.

## Global Constraints

- Canonical research identifiers are `workflow`, `plan_execute`, and `multi_agent`; `basic` and `deep` are migration-only aliases.
- All Agent orchestration, cycles, conditional routing, parallel fan-out, retries, interrupts, and checkpoint boundaries use LangGraph.
- Ordinary deterministic helpers such as validation, normalization, ranking, hashing, and formatting remain plain Python functions.
- Graph State contains only serializable business data and references; clients, connections, locks, futures, embeddings, and full evidence bodies are runtime dependencies or external records.
- The default response mode is `answer`; `report` is selected only for an explicit report request.
- Large tool results are stored by reference, and every surfaced citation resolves to an Evidence record.
- Distributed execution provides at-least-once delivery with checkpointed execution and idempotent side effects; it does not claim exactly-once execution.
- Existing uncommitted user changes must not be edited, staged, or committed as part of the refactor.

---

## Plan Decomposition

### Plan 1: Harness Foundation

**Document:** `docs/superpowers/plans/2026-09-10-agent-harness-foundation.md`

Creates the domain contracts, canonical research-mode names, Harness State, Runtime Context, Strategy Registry, and a compiled top-level runtime-graph skeleton driven by scripted child graphs. It does not route production API or Worker traffic yet.

**Exit gate:** The top-level runtime graph can initialize a turn, route each canonical research mode through the registry, isolate child state, and return a typed ResearchOutcome under an in-memory checkpointer.

### Plan 2: Tool Gateway and Evidence Store

**Document:** `docs/superpowers/plans/2026-09-10-tool-gateway-evidence-store.md`

Creates atomic research capability ports, ToolSpec, ToolRequest, ToolResult, middleware ordering, hierarchical budget reservations, idempotency ledger, cache/singleflight ownership, Evidence storage, and security policy adapters.

**Exit gate:** Scripted concurrent tool calls prove allowlist enforcement, no pre-validation budget charge, singleflight reuse, result offloading, and replay-safe idempotency.

### Plan 3: Workflow and Response Vertical Slice

**Document:** `docs/superpowers/plans/2026-09-12-workflow-response-vertical-slice.md`

Implements WorkflowResearchGraph, AnswerGraph, BriefGraph, ReportGraph, citation validation, explicit report intent, and the first production Application Service path through the top-level runtime graph.

**Exit gate:** A real API run using `workflow` returns a concise cited answer by default and a full report only when requested; legacy `basic` records remain readable.

Before enabling this production path, the Application Service must reject any invocation where `config.configurable.thread_id` differs from `ConversationState.thread_id`, so checkpoint tenancy has one authoritative identity.

### Plan 4: Plan-and-Execute strategy

Replaces the current Deep Python loop with plan, task selection, executor, tool, evaluation, repair, and replan nodes connected by explicit LangGraph routes.

**Exit gate:** `plan_execute` supports bounded replanning and checkpoint resume without any handwritten orchestration loop; legacy `deep` records remain readable.

### Plan 5: Multi-Agent strategy

Rebuilds the Supervisor and Researcher paths as nested LangGraph subgraphs, uses `Send` for isolated concurrent assignments, and returns only typed ResearchOutcome data to the top-level runtime graph.

**Exit gate:** One Researcher failure remains task-local, completed sibling work survives retry, and Supervisor cannot invoke network tools.

### Plan 6: Conversation and Memory Lifecycle

Adds multi-turn invocation, intent routing, sliding-window context, structured dynamic compression, LangGraph Store namespaces, deterministic recall policy, evidence/fact/preference/episode writes, versioned updates, and forgetting.

**Exit gate:** The six memory questions—when to store, what to store, how to organize, when to recall, how to update, and how to forget—each have executable policy tests, and follow-ups can answer or incrementally research in the same thread.

### Plan 7: MySQL and Distributed Recovery

Adds MySQL-backed run records, events, checkpoints, long-term Store records, and tool execution ledger; retains Redis Streams for delivery and wakeups; adds leases, recovery scanning, cancellation, and selected interrupts.

**Exit gate:** Forced crashes after planning, tool execution, partial researcher completion, writing, and memory commit resume from a durable checkpoint without repeating a completed side effect.

### Plan 8: Observability, Evaluation, and Cutover

Adds structured events, traces, metrics, research-mode comparison datasets, memory and compression evaluations, final API/UI naming changes, documentation, migration scripts, and verified resume/interview material.

**Exit gate:** All traffic uses the top-level runtime graph, old orchestration entry points are removed, the complete non-real suite passes, and repeatable research-mode quality/cost/latency results are documented without unsupported production claims.

## Delivery Rules

1. Execute plans in numeric order.
2. Each plan begins from a green `uv run pytest -m "not real"` baseline.
3. Each task follows red-green-refactor and ends with a focused commit.
4. Do not delete an old production path until its replacement passes contract, integration, and recovery tests.
5. At every plan exit gate, run the full non-real suite and review the diff before starting the next plan.
6. If an implementation decision changes an approved cross-plan contract, update the design spec and affected later plans in the same commit.
