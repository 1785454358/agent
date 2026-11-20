from __future__ import annotations

import inspect
import json
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ResearchMode
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.strategies.multi_agent.graph import build_multi_agent_research_graph
from strategies.fixtures import (
    ScriptedModelGateway,
    build_gateway_fixture,
    evaluation_payload_from_view,
)


def _research_input(question: str) -> dict[str, Any]:
    return {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": question,
        "conversation_summary": {},
        "prior_evidence_ids": [],
        "unresolved_gaps": [],
        "budget": {},
        "current_date": "2026-09-13",
        "timezone": "Asia/Shanghai",
    }


def _evaluation_with_prompt_evidence(prompt: str, *, action: str = "complete") -> str:
    return json.dumps(evaluation_payload_from_view(prompt, action=action))


async def _run_multi_agent(
    model: ScriptedModelGateway,
    fixture,
    *,
    question: str = "研究 Harness 演进",
    max_researchers: int = 5,
    max_follow_ups: int = 1,
    checkpointer=None,
    topic_graph=None,
):
    graph = build_multi_agent_research_graph(
        topic_graph or build_research_agent_graph(),
        max_researchers=max_researchers,
        max_follow_ups=max_follow_ups,
        checkpointer=checkpointer,
    )
    result = await graph.ainvoke(
        _research_input(question),
        config={"configurable": {"thread_id": "ma-thread"}} if checkpointer else None,
        context=fixture.context,
    )
    return result


















class _UnfinishedPlanTopicGraph:
    """Delegates to the real topic graph but reports an open plan item."""

    def __init__(self, inner) -> None:
        self._inner = inner

    async def ainvoke(self, input_data, config=None, **kwargs):
        raw = await self._inner.ainvoke(input_data, config=config, **kwargs)
        outcome = raw["outcome"].model_copy(
            update={
                "plan_total": 2,
                "plan_completed": 1,
                "unfinished_todos": ["尚未完成的步骤"],
            }
        )
        return {"outcome": outcome}
