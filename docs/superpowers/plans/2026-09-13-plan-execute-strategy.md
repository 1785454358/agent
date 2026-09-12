# Plan-and-Execute Strategy Implementation Plan

> **Status:** Authored 2026-09-13 by the delivery agent (Roadmap Plan 4; no pre-existing plan doc existed).
> Strategy: strict red-green-refactor, focused commits, full non-real suite at the exit gate.

**Goal:** Replace the legacy Deep handwritten Python loop with a `PlanExecuteResearchGraph`: plan → task selection → topic execution → evaluation → bounded replanning, all expressed as explicit LangGraph nodes and conditional edges, returning a typed `ResearchOutcome(mode=PLAN_EXECUTE)`.

**Architecture:** Reuses the Plan 3 `ResearchTopicGraph` for each task's search+fetch work through `AgentToolGateway` (role `PLAN_EXECUTE_EXECUTOR`). Loop state (remaining plan, completed tasks, evidence, decision, replan count) lives in the private strategy state; only `ResearchOutcome` crosses into the top-level runtime graph.

**Spec:** `docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md` §9.2, §14, §16.

## Global constraints

- No handwritten orchestration loop: the module must contain no `while` cycles driving the graph; cycles exist only as LangGraph conditional edges.
- Replanning is bounded (`max_replans`, default 2) and enforced in the conditional edge, not in model discretion.
- Task plans are bounded (≤ 6 queries), stable-deduplicated, and never duplicate already-completed queries.
- One failed task becomes a gap; sibling evidence survives.
- Zero usable evidence terminates as `no_sources`; exhausted replans terminate as `max_replans_reached`; insufficient evaluation terminates as `insufficient_evidence`.
- Legacy `deep` records remain readable (already canonicalized via `RunRecord`); the legacy Deep factory path is untouched.

## Topology

```text
START → plan → select_task ─(has task)→ execute_task → evaluate ─(complete)────────→ finalize → END
                    ↑  └──(no task)──────────────────────→ evaluate ─(replan, budget)→ replan ──┘
                    └───────────────────────────────────────────────── (replan exhausted/block) → finalize
```

## Tasks

### Task 1: Contracts and state (`models.py`, `state.py`)
- `TaskPlan(queries: list[str])` strict, unique, ≤ 6, each ≤ 1000 chars.
- `ExecutorDecision(action: Literal["complete","replan","block"], reason, findings, unresolved_gaps)` strict.
- `PlanExecuteState` private TypedDict: flat input passthrough + loop channels with reducers (`merge_unique_strings`, `merge_topic_outcomes`, `add_executed_steps`).
- Add both models to the strict checkpoint allowlist.
- Tests: model bounds/validators, reducer behavior, strict-serializer round-trip.

### Task 2: Nodes and graph (`nodes.py`, `graph.py`)
- `build_plan_node(max_tasks)`, `select_task_node`, `build_execute_task_node(topic_graph, caller_id)`, `build_evaluate_node()`, `build_replan_node(max_tasks)`, `finalize_node`, routers `route_after_select` / `route_after_evaluate`.
- Planner failure → deterministic fallback `[question]`.
- Evaluate with zero evidence skips the model call and reports `no_evidence_collected`.
- Findings filtered to aggregated evidence; invalid citations dropped.
- `build_plan_execute_research_graph(topic_graph, *, max_tasks=6, max_replans=2, checkpointer=None)`.
- Tests: happy path; planner fallback; task failure gap + sibling evidence; zero evidence `no_sources`; replan loop bounded (`max_replans_reached`); evaluator parse failure → deterministic partial; findings cannot cite unknown evidence; loop-state channels persisted in checkpoint; no `while` in module source.

### Task 3: Registration and exit gate
- Export from `deeptrace.strategies`.
- Integration: `plan_execute` request through `ResearchApplicationService` + top-level graph reaches `ResearchOutcome(mode=PLAN_EXECUTE)` with real topic subgraph and gateway fixture.
- Full non-real suite + `compileall`.

## Deliberately deferred

- Budget-aware task selection and RetryPolicy wiring: Plan 7/8.
- Task-level parallelism (multi-task Send fan-out): the design keeps plan_execute sequential (replanning requires ordered feedback); documented decision.
