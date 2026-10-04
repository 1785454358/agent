"""Shared Agent Harness Runtime: context → model → tools → observe → policy."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from deeptrace.domain import ErrorCategory, ErrorRecord, ResearchTopicOutcome
from deeptrace.harness.agent_state import AgentExecutorState, TodoStatus, topic_input
from deeptrace.harness.agent_tools import (
    RESEARCH_TOOLS,
    WRITE_TODOS_TOOL,
    execute_batch,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.policies.agent_context import (
    ContextLimitError,
    message_tokens,
    prepare_messages_with_diagnostics,
)
from deeptrace.harness.policies.execution import ExecutionPolicy
from deeptrace.harness.token_budget import TokenBudgetConfig

RESEARCHER_ROLE = "researcher"
__all__ = ["WRITE_TODOS_TOOL", "build_research_agent_graph"]


def _error(code, category=ErrorCategory.FATAL):
    return ErrorRecord(
        code=code,
        category=category,
        source="agent",
        node="call_model",
        public_message=code,
    )


def _normalize_calls(response: AIMessage, state: AgentExecutorState) -> AIMessage:
    """Persist unique bounded identities before tools run; stable across replay."""
    used = {
        c["id"] for m in state.get("messages", []) for c in getattr(m, "tool_calls", [])
    }
    calls = []
    invalid = [
        {
            "name": c.get("name") or "unknown",
            "args": {"__invalid_arguments__": True},
            "id": c.get("id") or "",
        }
        for c in response.invalid_tool_calls
    ]
    for index, call in enumerate([*response.tool_calls, *invalid]):
        call = dict(call)
        identity = call.get("id") or ""
        if not identity or len(identity) > 128 or identity in used:
            identity = hashlib.sha256(
                f"{state.get('iteration', 0)}:{index}:{identity}".encode()
            ).hexdigest()
        used.add(identity)
        call["id"] = identity
        calls.append(call)
    return response.model_copy(update={"tool_calls": calls, "invalid_tool_calls": []})


def build_research_agent_graph(
    *,
    max_iterations: int = 8,
    consecutive_error_limit: int = 3,
    completion_nudge_limit: int = 2,
    max_discovered_urls: int = 200,
    max_tool_concurrency: int = 4,
    token_budget: TokenBudgetConfig | None = None,
    checkpointer=None,
) -> CompiledStateGraph:
    policy = ExecutionPolicy(
        max_iterations, consecutive_error_limit, completion_nudge_limit
    )
    budget = token_budget or TokenBudgetConfig()
    if max_discovered_urls < 1 or max_tool_concurrency < 1:
        raise ValueError("Tool limits must be positive")

    def prepare_context(state: AgentExecutorState) -> dict[str, Any]:
        stop = policy.stop(state)
        if stop:
            return {"stop_reason": stop}
        return {}

    async def call_model(
        state: AgentExecutorState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        try:
            messages, note_diagnostics = prepare_messages_with_diagnostics(
                state,
                RESEARCH_TOOLS,
                budget,
                remaining_iterations=max_iterations - state.get("iteration", 0),
            )
        except ContextLimitError:
            return {
                "stop_reason": "context_limit",
                "failures": [*state.get("failures", []), _error("context_limit")],
            }

        updates: dict[str, Any] = {
            "iteration": state.get("iteration", 0) + 1,
            "research_finding_diagnostics": list(
                dict.fromkeys(
                    [
                        *(state.get("research_finding_diagnostics") or []),
                        *note_diagnostics,
                    ]
                )
            )[:100],
        }
        try:
            try:
                await runtime.context.event_sink.emit(
                    "agent.context_view",
                    {
                        "run_id": topic_input(state).run_id,
                        "branch": topic_input(state).query,
                        "iteration": updates["iteration"],
                        "estimated_input_tokens": message_tokens(
                            messages, RESEARCH_TOOLS
                        ),
                        "diagnostics": note_diagnostics,
                    },
                )
            except Exception:
                logging.getLogger(__name__).warning(
                    "Context telemetry unavailable", exc_info=True
                )
            response = await runtime.context.model_gateway.invoke(
                role=RESEARCHER_ROLE,
                messages=messages,
                tools=RESEARCH_TOOLS,
            )
            if not isinstance(response, AIMessage):
                raise TypeError("Invalid model protocol")
            updates["messages"] = [_normalize_calls(response, state)]
        except asyncio.CancelledError:
            updates.update(
                stop_reason="cancelled",
                failures=[
                    *state.get("failures", []),
                    _error("cancelled", ErrorCategory.CANCELLED),
                ],
            )
        except Exception as exc:
            logging.getLogger(__name__).exception("Agent model boundary failed")
            updates.update(
                stop_reason="model_error",
                failures=[
                    *state.get("failures", []),
                    _error(
                        "model_error", getattr(exc, "category", ErrorCategory.FATAL)
                    ),
                ],
            )
        return updates

    async def execute_tools(
        state: AgentExecutorState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        return await execute_batch(
            state,
            runtime.context,
            max_concurrency=max_tool_concurrency,
            max_discovered_urls=max_discovered_urls,
        )

    def observe(state):
        # Tool observations are atomically merged by the preceding node. This
        # checkpoint boundary separates completed effects from policy decisions.
        last = (state.get("messages") or [None])[-1]
        finished = last is not None and last.type == "ai" and not last.tool_calls
        return {"stop_reason": policy.stop(state, model_finished=finished)}

    def route_model(state):
        if state.get("stop_reason"):
            return "finalize"
        return "execute_tools" if state["messages"][-1].tool_calls else "observe"

    def route_observation(state):
        if state.get("stop_reason"):
            return "finalize"
        return "nudge" if state["messages"][-1].type == "ai" else "prepare_context"

    def nudge(state):
        remaining = [
            t.content
            for t in state.get("todos", [])
            if t.status != TodoStatus.COMPLETED
        ]
        content = "请继续收集证据并完成计划。未完成项：" + (
            "；".join(remaining) or "仍需可靠证据"
        )
        return {
            "messages": [HumanMessage(content=content)],
            "completion_nudges": state.get("completion_nudges", 0) + 1,
        }

    def finalize(state: AgentExecutorState) -> dict[str, Any]:
        agent = policy.outcome(state)
        return {
            "outcome": ResearchTopicOutcome(
                query=topic_input(state).query,
                read_anchors=state.get("read_anchors") or [],
                read_anchor_diagnostics=state.get("read_anchor_diagnostics") or [],
                research_findings=state.get("research_findings") or [],
                research_finding_diagnostics=state.get("research_finding_diagnostics")
                or [],
                agent_outcome=agent,
                evidence_ids=agent.evidence_ids,
                attempted_urls=sorted(set(state.get("attempted_urls") or []))[:100],
                errors=state.get("errors", [])[-100:],
                executed_steps=agent.executed_steps,
                plan_total=agent.plan_total,
                plan_completed=agent.plan_completed,
                unfinished_todos=agent.unfinished_todos,
            )
        }

    builder = StateGraph(AgentExecutorState, context_schema=HarnessContext)
    for name, node in [
        ("prepare_context", prepare_context),
        ("call_model", call_model),
        ("execute_tools", execute_tools),
        ("observe", observe),
        ("nudge", nudge),
        ("finalize", finalize),
    ]:
        builder.add_node(name, node)
    builder.add_edge(START, "prepare_context")
    builder.add_conditional_edges(
        "prepare_context",
        lambda s: "finalize" if s.get("stop_reason") else "call_model",
    )
    builder.add_conditional_edges("call_model", route_model)
    builder.add_edge("execute_tools", "observe")
    builder.add_conditional_edges("observe", route_observation)
    builder.add_edge("nudge", "prepare_context")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer).with_config(
        {"recursion_limit": max_iterations * 5 + 10}
    )
