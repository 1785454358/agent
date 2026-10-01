from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
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
from deeptrace.tools.evidence_store import EvidenceDraft, InMemoryEvidenceStore


class RecordingGraph:
    """Stands in for the compiled top-level runtime graph."""

    def __init__(self, response_mode: ResponseMode = ResponseMode.ANSWER) -> None:
        self._response_mode = response_mode
        self.evidence_ids = ["evidence-1"]
        self.invocations: list[tuple[dict[str, Any], dict[str, Any] | None]] = []

    async def ainvoke(self, input_data, config=None, **kwargs):
        self.invocations.append((input_data, config))
        conversation = input_data["conversation"]
        turn = input_data["turn"]
        outcome = {
            "mode": turn["selected_mode"].value,
            "evidence_ids": self.evidence_ids,
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
                        {"evidence_id": item, "marker": f"[{index}]"}
                        for index, item in enumerate(self.evidence_ids, 1)
                    ],
                    "cited_evidence_ids": self.evidence_ids,
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


async def _seeded_context(graph: RecordingGraph) -> HarnessContext:
    store = InMemoryEvidenceStore()
    evidence = await store.ingest(
        "workspace-1",
        EvidenceDraft(
            canonical_url="https://example.com/harness",
            title="Harness",
            media_type="text/plain",
            body="Public harness evidence",
            fetched_at=datetime.now(UTC),
            source_quality=1.0,
        ),
    )
    graph.evidence_ids = [evidence.id]
    return replace(_context(), evidence_store=store)


@pytest.mark.asyncio
async def test_service_preserves_partial_research_even_with_usable_answer() -> None:
    class PartialGraph(RecordingGraph):
        async def ainvoke(self, input_data, config=None, **kwargs):
            result = await super().ainvoke(input_data, config=config, **kwargs)
            result["turn"]["status"] = ExecutionStatus.PARTIAL
            result["turn"]["research_outcome"].update(
                termination_reason="max_iterations",
                executed_steps=7,
                unresolved_gaps=["Missing comparison"],
            )
            return result

    graph = PartialGraph()
    context = await _seeded_context(graph)
    result = await ResearchApplicationService(graph).invoke(
        _request(),
        config=_config(),
        context=context,
    )
    assert result.status == "partial"
    assert result.termination_reason == "max_iterations"
    assert result.executed_steps == 7
    assert result.unresolved_gaps == ["Missing comparison"]
    assert result.response_outcome.partial_reason is None
    assert result.sources == ["https://example.com/harness"]


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


@pytest.mark.asyncio
async def test_service_invokes_graph_with_canonical_identity_and_returns_outcome() -> (
    None
):
    graph = RecordingGraph()
    service = ResearchApplicationService(graph)

    context = await _seeded_context(graph)
    outcome = await service.invoke(
        _request(), config=_config("thread-1"), context=context
    )

    assert outcome.response_outcome.response_mode is ResponseMode.ANSWER
    assert outcome.response_outcome.content == "回答 [1]"
    assert outcome.status == "completed"
    assert outcome.termination_reason == "completed"
    assert outcome.executed_steps == 2
    assert (outcome.run_id, outcome.thread_id) == ("run-1", "thread-1")
    assert len(graph.invocations) == 1
    initial, config = graph.invocations[0]
    assert initial["conversation"]["thread_id"] == "thread-1"
    assert initial["conversation"]["active_mode"] is ResearchMode.WORKFLOW
    assert initial["turn"]["run_id"] == "run-1"
    assert initial["turn"]["selected_mode"] is ResearchMode.WORKFLOW
    assert config["configurable"]["thread_id"] == "thread-1"


@pytest.mark.asyncio
async def test_service_applies_explicit_response_mode_override() -> None:
    graph = RecordingGraph()
    service = ResearchApplicationService(graph)

    context = await _seeded_context(graph)
    await service.invoke(
        _request(response_mode=ResponseMode.REPORT),
        config=_config("thread-1"),
        context=context,
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
            service.invoke(_request(), config=_config("thread-1"), context=_context())
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "running", "pending", "failed", "cancelled"])
async def test_service_rejects_nonterminal_success_result(status) -> None:
    class InvalidStatusGraph(RecordingGraph):
        async def ainvoke(self, *args, **kwargs):
            result = await super().ainvoke(*args, **kwargs)
            result["turn"]["status"] = status
            return result

    graph = InvalidStatusGraph()
    context = await _seeded_context(graph)
    with pytest.raises(RuntimeError, match="terminal status"):
        await ResearchApplicationService(graph).invoke(
            _request(), config=_config(), context=context
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["mode_switched", "citation_invalid"])
async def test_no_research_does_not_borrow_history_or_read_uncited_sources(
    reason,
) -> None:
    class DirectGraph(RecordingGraph):
        async def ainvoke(self, *args, **kwargs):
            result = await super().ainvoke(*args, **kwargs)
            result["turn"].update(status="partial", research_outcome=None)
            result["turn"]["response_outcome"].update(partial_reason=reason)
            return result

    graph = DirectGraph()
    graph.evidence_ids = []
    # Object store has no read API: no-citation responses must not call it.
    result = await ResearchApplicationService(graph).invoke(
        _request(), config=_config(), context=_context()
    )
    assert result.executed_steps == 0
    assert result.research_outcome is None
    assert result.unresolved_gaps == []
    assert result.sources == []
    assert result.termination_reason == (reason or "partial")


@pytest.mark.asyncio
async def test_partial_without_specific_reason_remains_partial() -> None:
    class PartialGraph(RecordingGraph):
        async def ainvoke(self, *args, **kwargs):
            result = await super().ainvoke(*args, **kwargs)
            result["turn"]["status"] = "partial"
            return result

    graph = PartialGraph()
    context = await _seeded_context(graph)
    result = await ResearchApplicationService(graph).invoke(
        _request(), config=_config(), context=context
    )
    assert result.status == "partial"
    assert result.termination_reason == "partial"


@pytest.mark.asyncio
async def test_service_rejects_missing_and_cross_workspace_citations() -> None:
    graph = RecordingGraph()
    context = await _seeded_context(graph)
    service = ResearchApplicationService(graph)
    with pytest.raises(KeyError):
        await service.invoke(
            _request(), config=_config(), context=replace(context, workspace_id="other")
        )
    graph.evidence_ids = ["missing"]
    with pytest.raises(KeyError):
        await service.invoke(_request(), config=_config(), context=context)


@pytest.mark.asyncio
async def test_service_preserves_response_failure_after_completed_research() -> None:
    class ResponseFailureGraph(RecordingGraph):
        async def ainvoke(self, *args, **kwargs):
            result = await super().ainvoke(*args, **kwargs)
            result["turn"]["status"] = "partial"
            result["turn"]["response_outcome"]["partial_reason"] = "citation_invalid"
            return result

    graph = ResponseFailureGraph()
    context = await _seeded_context(graph)
    result = await ResearchApplicationService(graph).invoke(
        _request(), config=_config(), context=context
    )
    assert result.status == "partial"
    assert result.termination_reason == "citation_invalid"
    assert result.research_outcome.termination_reason == "completed"
    assert result.executed_steps == 2


@pytest.mark.asyncio
async def test_service_projects_ordered_metadata_once_and_copies_gaps() -> None:
    class TrackingStore(InMemoryEvidenceStore):
        reads = 0

        async def get_many(self, *args):
            self.reads += 1
            return await super().get_many(*args)

        async def read_body(self, *args):
            raise AssertionError("result projection must not read plaintext bodies")

    class GapGraph(RecordingGraph):
        async def ainvoke(self, *args, **kwargs):
            result = await super().ainvoke(*args, **kwargs)
            result["turn"]["status"] = "partial"
            result["turn"]["research_outcome"].update(
                termination_reason="max_iterations", unresolved_gaps=["Missing fact"]
            )
            result["turn"]["response_outcome"]["partial_reason"] = "citation_invalid"
            return result

    store = TrackingStore()
    ids = []
    for url in ["https://example.com/b", "https://example.com/a"]:
        evidence = await store.ingest(
            "workspace-1",
            EvidenceDraft(
                canonical_url=url,
                title="Source",
                media_type="text/plain",
                body=url,
                fetched_at=datetime.now(UTC),
                source_quality=1.0,
            ),
        )
        ids.append(evidence.id)
    graph = GapGraph()
    graph.evidence_ids = ids
    result = await ResearchApplicationService(graph).invoke(
        _request(), config=_config(), context=replace(_context(), evidence_store=store)
    )
    assert result.sources == ["https://example.com/b", "https://example.com/a"]
    assert store.reads == 1
    assert result.termination_reason == "max_iterations"
    result.unresolved_gaps.append("Caller edit")
    assert result.research_outcome.unresolved_gaps == ["Missing fact"]
