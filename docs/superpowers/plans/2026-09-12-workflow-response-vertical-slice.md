# Workflow and Response Vertical Slice Implementation Plan

> **For agentic workers:** Execute task-by-task with strict red-green-refactor. Each task requires a specification review and a code-quality review before commit.

> **Status (2026-09-13):** COMPLETE. All seven tasks delivered; exit gate locked by
> `backend/tests/integration/test_workflow_response_exit_gate.py` (487 non-real tests green).
> Contract decisions made during implementation are recorded in
> `docs/superpowers/plans/2026-09-13-harness-implementation-decisions.md`.

**Goal:** Deliver the first production-shaped path through the Agent Harness: a LangGraph Workflow research strategy followed by Answer, Brief, or explicitly requested Report output with validated Evidence citations.

**Architecture:** `build_agent_runtime_graph` remains the only top-level orchestration entry point. It invokes a registered `WorkflowResearchGraph`, whose LangGraph fan-out calls a reusable `ResearchTopicGraph`; all external capabilities pass through `AgentToolGateway`. Research returns only `ResearchOutcome`, response subgraphs read Evidence by reference, and `ResearchApplicationService` validates execution identity before invoking the graph.

**Tech Stack:** Python 3.11+, Pydantic 2, LangGraph 1.x, LangChain messages, asyncio, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md`

## Global constraints

- Use `ResearchMode.WORKFLOW`; `basic` remains a read/migration alias only.
- Use the terms Agent Harness, top-level runtime graph, research mode, and strategy subgraph. Do not introduce a special Harness graph type or revive superseded mode-label vocabulary.
- All planning, fan-out, conditional routing, strategy execution, and response selection use LangGraph nodes and edges.
- Plain Python remains appropriate for validation, normalization, hashing, citation filtering, and formatting.
- Graph State contains serializable business data and Evidence references only. Full Evidence bodies, clients, locks, futures, and stores remain runtime dependencies.
- Every search, fetch, and memory lookup enters `AgentToolGateway`; strategy nodes must not call providers directly.
- Default output is `answer`. `report` is selected only from an explicit user request; research depth and output form remain independent.
- A citation can be emitted only when its Evidence record was loaded into the current response context.
- `config.configurable.thread_id` must equal `ConversationState.thread_id` before graph execution.
- The first slice uses in-memory checkpoint/store implementations in tests. MySQL durability remains Plan 7 work.
- Keep existing Basic production code runnable until this plan's exit gate passes; do not delete old modules in this plan.

---

### Task 1: Add execution identity and response contracts

**Files:**

- Modify: `backend/src/deeptrace/domain/execution.py`
- Create: `backend/src/deeptrace/domain/response.py`
- Modify: `backend/src/deeptrace/domain/__init__.py`
- Modify: `backend/src/deeptrace/harness/state.py`
- Modify: `backend/src/deeptrace/harness/checkpoint.py`
- Test: `backend/tests/domain/test_response.py`
- Modify: `backend/tests/domain/test_execution.py`
- Modify: `backend/tests/harness/test_state.py`

**Interfaces:**

- `ResearchInput` gains required, bounded `run_id: str` and `thread_id: str` fields.
- `CitationRef(evidence_id: str, marker: str)` identifies one citation without copying source content.
- `ResponseInput(question, response_mode, research_outcome, active_evidence_ids)` is the shared input for all response subgraphs.
- `ResponseOutcome(response_mode, content, citations, cited_evidence_ids, partial_reason)` is the only response result merged into Harness State.
- `TurnState.response_outcome` is reset to `None` by every `new_turn` call.

- [x] Write failing tests proving identity is required, citation IDs are unique and bounded, response content is bounded, invalid success/reference combinations fail, and response contracts round-trip through the strict checkpoint serializer.
- [x] Run `backend/tests/domain/test_response.py`, `test_execution.py`, and `backend/tests/harness/test_state.py`; confirm RED.
- [x] Implement the smallest strict Pydantic contracts with `extra="forbid"` and add exact public/serializer exports.
- [x] Update `_research_input` later consumers through test fixtures without adding fallback IDs.
- [x] Run focused tests and `backend/tests/harness/test_checkpoint.py`.
- [x] Review for unbounded text/list fields and commit `feat: define research response contracts`.

### Task 2: Build the reusable ResearchTopicGraph

**Files:**

- Create: `backend/src/deeptrace/strategies/__init__.py`
- Create: `backend/src/deeptrace/strategies/topic/__init__.py`
- Create: `backend/src/deeptrace/strategies/topic/state.py`
- Create: `backend/src/deeptrace/strategies/topic/graph.py`
- Create: `backend/src/deeptrace/strategies/topic/nodes.py`
- Test: `backend/tests/strategies/topic/test_graph.py`
- Test: `backend/tests/strategies/topic/test_state.py`

**Interfaces:**

- `ResearchTopicInput(run_id, thread_id, query, max_pages, mode, caller_id)` is serializable.
- `ResearchTopicOutcome(query, evidence_ids, attempted_urls, errors, executed_steps)` contains references and stable errors only.
- `build_research_topic_graph()` compiles `search → select_urls → Send(fetch_page × N) → finalize`.
- Tool call IDs are deterministic hashes of run, graph node, query, URL, and ordinal. They remain stable across checkpoint replay.

- [x] Write failing topology/state tests using a recording `ToolGateway`; prove search happens before URL selection, `Send` creates isolated fetch branches, and only fetched Evidence IDs reach the outcome.
- [x] Add rejection tests for malformed search previews, duplicate/unsafe URLs, empty results, partial fetch failure, and max-page bounds.
- [x] Confirm RED because the strategy package does not exist.
- [x] Implement state reducers that stable-deduplicate Evidence IDs and collect branch-local errors without sharing mutable lists.
- [x] Implement nodes that construct `ToolCaller(role=WORKFLOW_GRAPH, mode=WORKFLOW)` and typed `ToolRequest` values, then call only `runtime.context.tool_gateway.execute(...)`.
- [x] Build `UrlAuthorization` only from normalized URLs returned by the search result; never authorize arbitrary model-generated URLs in this graph.
- [x] Compile with `StateGraph(..., context_schema=HarnessContext)` and LangGraph `Send`; do not use `asyncio.gather` for orchestration.
- [x] Run topic graph tests and Tool Gateway tests.
- [x] Review private branch state isolation and commit `feat: add research topic subgraph`.

### Task 3: Implement WorkflowResearchGraph

**Files:**

- Create: `backend/src/deeptrace/strategies/workflow/__init__.py`
- Create: `backend/src/deeptrace/strategies/workflow/state.py`
- Create: `backend/src/deeptrace/strategies/workflow/models.py`
- Create: `backend/src/deeptrace/strategies/workflow/nodes.py`
- Create: `backend/src/deeptrace/strategies/workflow/graph.py`
- Test: `backend/tests/strategies/workflow/test_graph.py`
- Test: `backend/tests/strategies/workflow/test_nodes.py`

**Interfaces:**

- `WorkflowState` owns `input`, `queries`, isolated topic outcomes, Evidence references, findings, gaps, step count, and final `ResearchOutcome`.
- `QueryPlan(queries: list[str])` is strict, stable-deduplicated, and bounded to the configured query count.
- `WorkflowEvaluation(findings, unresolved_gaps, sufficient)` cannot cite Evidence outside the aggregated topic outcomes.
- `build_workflow_research_graph(topic_graph, *, query_limit=3)` returns a `ResearchStrategyGraph` compatible compiled graph.

- [x] Write failing graph tests for `START → plan_queries → Send(research_topic × N) → evaluate → finalize → END`.
- [x] Prove planner failure deterministically falls back to the normalized user question and does not create a handwritten retry loop.
- [x] Prove one topic failure is retained as a gap while sibling Evidence survives; zero usable Evidence yields `partial/no_sources` rather than a false completed result.
- [x] Confirm RED.
- [x] Implement planner and evaluator model nodes through `HarnessContext.model_gateway`; parse strict models once and route malformed output to deterministic fallback/partial results.
- [x] Invoke the compiled topic subgraph with inherited Runtime Context and config so child checkpoints receive a namespace.
- [x] Validate every `Finding.evidence_ids` set against aggregated Evidence before constructing `ResearchOutcome(mode=WORKFLOW, ...)`.
- [x] Run Workflow, topic, Gateway, and strict serializer tests.
- [x] Review that the graph contains no provider calls, manual orchestration loop, or full Evidence body in state; commit `feat: add workflow research strategy`.

### Task 4: Add citation validation and three response subgraphs

**Files:**

- Create: `backend/src/deeptrace/responses/__init__.py`
- Create: `backend/src/deeptrace/responses/citations.py`
- Create: `backend/src/deeptrace/responses/models.py`
- Create: `backend/src/deeptrace/responses/state.py`
- Create: `backend/src/deeptrace/responses/graph.py`
- Test: `backend/tests/responses/test_citations.py`
- Test: `backend/tests/responses/test_graph.py`

**Interfaces:**

- `select_response_mode(user_input: str) -> ResponseMode` is a deterministic boundary policy: explicit report wording selects `REPORT`, explicit summary/brief wording selects `BRIEF`, otherwise `ANSWER`.
- `validate_citations(draft, loaded_evidence_ids) -> ResponseOutcome` removes unknown citations and never invents replacements.
- `build_answer_graph()`, `build_brief_graph()`, and `build_report_graph()` share the same load/generate/validate topology and vary only prompt policy and output bounds.
- Response graphs call `EvidenceStore.get_many(tenant_id, ids)` and bounded `read_body`; they never call network tools.

- [x] Write failing policy tests including ordinary questions containing the word “report” as a noun versus explicit commands such as “生成报告”.
- [x] Write failing citation tests for valid, duplicate, unknown, missing, and cross-tenant Evidence IDs.
- [x] Write graph tests proving Answer is concise by policy, Brief is structured but bounded, and Report receives the formal-report prompt only after explicit selection.
- [x] Confirm RED.
- [x] Implement a shared response graph factory with three named builders rather than three copied graphs.
- [x] Load only `ResponseInput.active_evidence_ids`, cap per-source body/context size, and include stable Evidence IDs in model context.
- [x] If generation fails, return a deterministic Evidence-backed partial response; never present an uncited formal report as complete.
- [x] Run response, Evidence Store, and Tool policy tests.
- [x] Review citation ownership and prompt separation; commit `feat: add evidence-backed response graphs`.

### Task 5: Extend the top-level runtime graph through response generation

**Files:**

- Modify: `backend/src/deeptrace/harness/registry.py`
- Modify: `backend/src/deeptrace/harness/graph.py`
- Modify: `backend/src/deeptrace/harness/state.py`
- Modify: `backend/src/deeptrace/harness/__init__.py`
- Modify: `backend/tests/harness/test_graph.py`
- Create: `backend/tests/harness/test_workflow_response_slice.py`

**Interfaces:**

- Add a `ResponseGraphRegistry` keyed by canonical `ResponseMode`, with duplicate/raw-string rejection equivalent to `StrategyRegistry`.
- `build_agent_runtime_graph(strategy_registry, response_registry, checkpointer=None)` routes `initialize_turn → selected research strategy → select_response_mode → selected response graph → finalize_turn`.
- `_research_input` copies the authoritative run/thread IDs from Harness State.
- Only `ResearchOutcome` and `ResponseOutcome` cross child-graph boundaries.

- [x] Write failing registry tests and update scripted child graphs for the new identity fields.
- [x] Write a failing integration test proving the same Workflow outcome routes to Answer by default and Report only for an explicit request.
- [x] Add a test proving private Workflow/response state remains visible only in child checkpoints and never leaks into `HarnessState`.
- [x] Confirm RED.
- [x] Implement typed response registration and top-level routing through the existing `build_agent_runtime_graph` builder.
- [x] Pass `context=runtime.context` when invoking each child graph and validate the child result before merging.
- [x] Finalize status from both outcomes: completed only when research and response contracts are usable; otherwise partial/failed according to stable termination reasons.
- [x] Run all Harness, Workflow, response, and checkpoint tests.
- [x] Review state ownership and commit `feat: connect workflow and response subgraphs`.

### Task 6: Add the ResearchApplicationService identity boundary

**Files:**

- Create: `backend/src/deeptrace/application/__init__.py`
- Create: `backend/src/deeptrace/application/research.py`
- Test: `backend/tests/application/test_research_service.py`
- Modify: `backend/src/deeptrace/runtime/models.py`
- Modify: `backend/src/deeptrace/runtime/protocol.py`
- Modify: `backend/src/deeptrace/runtime/local.py`
- Modify: `backend/src/deeptrace/api.py`
- Modify: `backend/tests/runtime/test_local.py`
- Modify: `backend/tests/api/test_api.py`

**Interfaces:**

- `ApplicationResearchRequest(run_id, thread_id, question, mode, response_mode=None)` normalizes legacy mode aliases only at construction boundaries.
- `ResearchApplicationService.invoke(request, *, config, context) -> ResponseOutcome` owns initial Harness State construction and top-level graph invocation.
- The service raises `ExecutionIdentityMismatch` before invocation when config lacks `thread_id` or it differs from `request.thread_id`.
- Public creation accepts canonical `workflow`, `plan_execute`, and `multi_agent`; existing persisted `basic/deep` records remain readable through normalization.

- [x] Write failing service tests for missing/mismatched/matching thread IDs and prove mismatch produces zero model/tool/event calls.
- [x] Write failing API/runtime tests for canonical `workflow`, default Answer, explicit Report, and legacy record deserialization.
- [x] Confirm RED.
- [x] Implement the application boundary and a Workflow-enabled local runtime adapter without deleting the legacy Basic factory path.
- [x] Keep `RunRecord` migration validation explicit: normalize legacy values when reading, write canonical values for new records.
- [x] Return response content and cited source URLs through the existing API shape while preserving structured `ResponseOutcome` internally.
- [x] Run application, API, Local runtime, persistence, and legacy Basic tests.
- [x] Review that API/Runtime code does not know Workflow private state; commit `feat: route workflow runs through application service`.

### Task 7: Lock the Plan 3 exit gate

**Files:**

- Create: `backend/tests/integration/test_workflow_response_exit_gate.py`
- Modify: `backend/tests/test_module_layout.py`
- Modify: `docs/superpowers/plans/2026-09-10-langgraph-agent-harness-roadmap.md`

**Interfaces:**

- Public exports include the Workflow strategy builder, three response builders, response contracts, and `ResearchApplicationService`.
- Old `basic` modules remain importable but are not the implementation selected for new canonical `workflow` requests.

- [x] Build an in-memory end-to-end fixture with scripted model responses, real LangGraph subgraphs, `AgentToolGateway`, in-memory Evidence/execution/cache/budget services, and `InMemorySaver`.
- [x] Assert a default Workflow request performs typed tool calls, stores page bodies only in Evidence Store, returns a concise cited Answer, and preserves private child checkpoints.
- [x] Assert an explicit report request uses the same research strategy and Evidence but routes to Report output.
- [x] Assert invalid config thread identity fails before all side effects and a legacy `basic` record remains readable as Workflow.
- [x] Run focused exit-gate tests.
- [x] Run `backend/.venv/Scripts/python.exe -m pytest -m "not real" -q`.
- [x] Run `backend/.venv/Scripts/python.exe -m compileall -q backend/src backend/tests` from repository root.
- [x] Review the complete Plan 3 diff for raw bodies in State/events, direct provider access, duplicate retry ownership, invalid citations, and old terminology.
- [x] Commit `test: lock workflow response vertical slice`.

---

## Plan 3 exit gate

- [x] Canonical `workflow` uses the new Workflow strategy subgraph through `build_agent_runtime_graph`.
- [x] Query and page fan-out use LangGraph `Send`, not manual orchestration loops.
- [x] All external search/fetch calls pass through `AgentToolGateway`.
- [x] Full page bodies exist only in Evidence Store; strategy/Harness checkpoints contain references.
- [x] Default output is Answer; Report requires explicit intent.
- [x] Every surfaced citation was loaded from the current tenant's Evidence records.
- [x] Application Service rejects thread identity mismatch before side effects.
- [x] Existing Basic, Plan-and-Execute, and Multi-Agent production paths remain runnable.
- [x] Legacy `basic` and `deep` persisted identifiers remain readable while new writes are canonical.
- [x] Full non-real tests and compile checks pass.

## Deliberately deferred

- Plan-and-Execute migration and removal of its handwritten loop: Plan 4.
- Multi-Agent Supervisor/Researcher migration: Plan 5.
- Sliding-window conversation compression and long-term memory lifecycle: Plan 6.
- MySQL checkpoint/Evidence/ledger adapters and Redis recovery: Plan 7.
- Automatic mode selection and cross-mode evaluation: after Plan 8 baselines.
