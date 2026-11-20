from __future__ import annotations

import json
import re
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from deeptrace.domain import ResearchInput, ResearchMode
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.strategies.workflow.graph import build_workflow_research_graph
from strategies.fixtures import (
    ScriptedModelGateway,
    build_gateway_fixture,
    evaluation_payload_from_view,
)


def _research_input(question: str = "研究 LangGraph Harness") -> dict[str, Any]:
    return ResearchInput(
        run_id="run-1",
        thread_id="thread-1",
        question=question,
        current_date="2026-09-12",
        timezone="Asia/Shanghai",
    ).model_dump(mode="json")


def _evidence_ids_from_prompt(prompt: str) -> list[str]:
    return sorted(set(re.findall(r"evidence-[0-9a-f]+", prompt)))


def _evaluation_with_prompt_evidence(prompt: str, *, sufficient: bool) -> str:
    return json.dumps(evaluation_payload_from_view(prompt, sufficient=sufficient))


async def _run_workflow(
    model: ScriptedModelGateway,
    fixture,
    *,
    question: str = "研究 LangGraph Harness",
    query_limit: int = 3,
    checkpointer=None,
    topic_graph=None,
):
    topic_graph = topic_graph or build_research_agent_graph()
    graph = build_workflow_research_graph(
        topic_graph, query_limit=query_limit, checkpointer=checkpointer
    )
    config = (
        {"configurable": {"thread_id": "workflow-thread"}} if checkpointer else None
    )
    result = await graph.ainvoke(
        _research_input(question), config=config, context=fixture.context
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
