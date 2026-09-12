from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from deeptrace.application.research import (
    ApplicationResearchRequest,
    ExecutionIdentityMismatch,
    ResearchApplicationService,
)
from deeptrace.domain import ExecutionStatus, ResearchMode, ResponseMode
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.state import new_conversation, new_turn


class RecordingGraph:
    """Stands in for the compiled top-level runtime graph."""

    def __init__(self, response_mode: ResponseMode = ResponseMode.ANSWER) -> None:
        self._response_mode = response_mode
        self.invocations: list[tuple[dict[str, Any], dict[str, Any] | None]] = []

    async def ainvoke(self, input_data, config=None, **kwargs):
        self.invocations.append((input_data, config))
        conversation = input_data["conversation"]
        turn = input_data["turn"]
        outcome = {
            "mode": turn["selected_mode"].value,
            "evidence_ids": ["evidence-1"],
            "findings": [],
            "unresolved_gaps": [],
            "executed_steps": 2,
            "termination_reason": "completed",
        }
        return {
            "conversation": conversation,
            "turn": {
                **turn,
                "status": ExecutionStatus.COMPLETED,
                "research_outcome": outcome,
                "response_outcome": {
                    "response_mode": self._response_mode.value,
                    "content": "回答 [1]",
                    "citations": [
                        {"evidence_id": "evidence-1", "marker": "[1]"}
                    ],
                    "cited_evidence_ids": ["evidence-1"],
                },
            },
        }


def _request(**overrides: Any) -> ApplicationResearchRequest:
    values: dict[str, Any] = {
        "run_id": "run-1",
        "thread_id": "thread-1",
        "question": "研究 Harness",
        "mode": ResearchMode.WORKFLOW,
    }
    values.update(overrides)
    return ApplicationResearchRequest(**values)


def _config(thread_id: str | None = "thread-1") -> dict[str, Any]:
    if thread_id is None:
        return {"configurable": {}}
    return {"configurable": {"thread_id": thread_id}}


def _context() -> HarnessContext:
    return HarnessContext(
        user_id="user-1",
        workspace_id="workspace-1",
        model_gateway=object(),
        tool_gateway=object(),
        evidence_store=object(),
        event_sink=object(),
        clock=object(),
    )


def test_request_normalizes_legacy_mode_aliases_at_boundary() -> None:
    assert _request(mode="basic").mode is ResearchMode.WORKFLOW
    assert _request(mode="deep").mode is ResearchMode.PLAN_EXECUTE
    assert _request(mode="workflow").mode is ResearchMode.WORKFLOW
    with pytest.raises(ValidationError):
        _request(mode="agent")


def test_service_rejects_missing_thread_id_before_side_effects() -> None:
    graph = RecordingGraph()
    service = ResearchApplicationService(graph)

    with pytest.raises(ExecutionIdentityMismatch, match="thread_id"):
        import asyncio

        asyncio.run(
            service.invoke(_request(), config=_config(None), context=_context())
        )
    assert graph.invocations == []


def test_service_rejects_mismatched_thread_id_before_side_effects() -> None:
    graph = RecordingGraph()
    service = ResearchApplicationService(graph)

    with pytest.raises(ExecutionIdentityMismatch, match="does not match"):
        import asyncio

        asyncio.run(
            service.invoke(
                _request(thread_id="thread-1"),
                config=_config("thread-2"),
                context=_context(),
            )
        )
    assert graph.invocations == []


def test_service_invokes_graph_with_canonical_identity_and_returns_outcome() -> None:
    import asyncio

    graph = RecordingGraph()
    service = ResearchApplicationService(graph)

    outcome = asyncio.run(
        service.invoke(
            _request(), config=_config("thread-1"), context=_context()
        )
    )

    assert outcome.response_mode is ResponseMode.ANSWER
    assert outcome.content == "回答 [1]"
    assert len(graph.invocations) == 1
    initial, config = graph.invocations[0]
    assert initial["conversation"]["thread_id"] == "thread-1"
    assert initial["conversation"]["active_mode"] is ResearchMode.WORKFLOW
    assert initial["turn"]["run_id"] == "run-1"
    assert initial["turn"]["selected_mode"] is ResearchMode.WORKFLOW
    assert config["configurable"]["thread_id"] == "thread-1"


def test_service_applies_explicit_response_mode_override() -> None:
    import asyncio

    graph = RecordingGraph()
    service = ResearchApplicationService(graph)

    asyncio.run(
        service.invoke(
            _request(response_mode=ResponseMode.REPORT),
            config=_config("thread-1"),
            context=_context(),
        )
    )

    _initial, config = graph.invocations[0]
    assert config["configurable"]["response_mode_override"] is ResponseMode.REPORT


def test_service_requires_a_response_outcome_from_the_graph() -> None:
    import asyncio

    class NoResponseGraph(RecordingGraph):
        async def ainvoke(self, input_data, config=None, **kwargs):
            result = await super().ainvoke(input_data, config=config, **kwargs)
            result["turn"]["response_outcome"] = None
            return result

    service = ResearchApplicationService(NoResponseGraph())

    with pytest.raises(RuntimeError, match="response outcome"):
        asyncio.run(
            service.invoke(
                _request(), config=_config("thread-1"), context=_context()
            )
        )
