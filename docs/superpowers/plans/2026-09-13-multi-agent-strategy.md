# Multi-Agent Strategy Implementation Plan

> **Status:** Authored 2026-09-13 by the delivery agent (Roadmap Plan 5; no pre-existing plan doc existed).

**Goal:** Rebuild Supervisor/Researcher as nested LangGraph subgraphs: `supervisor_plan → Send(researcher × N) → aggregate → supervisor_evaluate → (follow_up bounded) → finalize`, returning typed `ResearchOutcome(mode=MULTI_AGENT)`.

**Architecture:** Researchers ARE instances of the reusable `ResearchTopicGraph` invoked via LangGraph `Send` with private per-researcher branch state (role `MULTI_AGENT_RESEARCHER`, caller id `researcher-{index}`). The Supervisor uses only the model gateway and evidence store reads — it never touches the Tool Gateway, so it structurally cannot invoke network tools.

## Constraints

- One researcher failure stays task-local: its query becomes a gap; sibling evidence survives.
- Follow-up rounds are bounded (`max_follow_ups`, default 1), enforced in a conditional edge.
- Assignments bounded (≤ 5 per round), stable-deduplicated against already-dispatched queries.
- All loop state (assignments, round, researcher outcomes, evaluation) is checkpointed; only `ResearchOutcome` crosses the boundary.
- No handwritten orchestration loops (`while`) in module source.

## Tasks

1. **Contracts/state:** `SupervisorAssignment` not needed as a model (queries are strings); `SupervisorEvaluation(action: Literal["complete","follow_up"], reason, findings, unresolved_gaps)` strict; `MultiAgentState` with reducers; serializer allowlist.
2. **Nodes/graph:** `build_supervisor_plan_node(max_researchers)`, researcher branch node (wraps topic graph), `aggregate_node`, `build_supervisor_evaluate_node`, `build_follow_up_node`, `build_finalize_node`, routers; `build_multi_agent_research_graph(topic_graph, *, max_researchers=5, max_follow_ups=1, checkpointer=None)`.
3. **Tests:** happy path with concurrent researchers; researcher failure task-local; follow-up bounded (`max_follow_ups_reached`); supervisor never reaches the tool gateway; branch isolation (per-researcher caller ids); checkpoint keeps loop state and no bodies; no `while` in source; integration through the application service.
