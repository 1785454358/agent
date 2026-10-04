from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from deeptrace.application.agent_adapter import HarnessResearchRunner
from deeptrace.application.result import ApplicationRunResult
from deeptrace.domain import ResearchOutcome, ResponseOutcome
from deeptrace.runtime.models import RunRecord


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,reason,gaps",
    [
        ("partial", "max_iterations", ["Missing comparison"]),
        ("completed", "completed", []),
    ],
)
async def test_worker_maps_authoritative_result_without_reading_sources(
    status, reason, gaps
):
    class Application:
        async def invoke(self, request, *, config, context):
            assert config["configurable"]["thread_id"] == "thread-1"
            return ApplicationRunResult(
                run_id=request.run_id,
                thread_id=request.thread_id,
                status=status,
                research_outcome=ResearchOutcome(
                    mode="workflow",
                    executed_steps=7,
                    termination_reason=reason,
                    unresolved_gaps=gaps,
                ),
                response_outcome=ResponseOutcome(
                    response_mode="answer",
                    content="Answer [1]",
                    citations=[{"evidence_id": "evidence-1", "marker": "[1]"}],
                    cited_evidence_ids=["evidence-1"],
                ),
                termination_reason=reason,
                executed_steps=7,
                unresolved_gaps=gaps,
                sources=["https://example.com/source"],
            )

    runner = HarnessResearchRunner(object())
    def context_factory(run_id, on_event):
        on_event("replanning.completed", {"round": 2, "tasks_json": '["补充论文"]', "api_key": "secret"})
        return object()

    runner._bundle = SimpleNamespace(service=Application(), context_factory=context_factory)
    events = []
    result = await runner(
        RunRecord(
            id="run-1",
            thread_id="thread-1",
            question="Question",
            mode="workflow",
            created_at=datetime.now(UTC),
        ),
        events.append,
    )
    assert result.status == status
    assert result.termination_reason == reason
    assert result.steps == 7
    assert result.unresolved_gaps == gaps
    assert result.sources == ["https://example.com/source"]
    assert result.answer == "Answer [1]"
    assert events[-1].message == (
        "研究已完成" if status == "completed" else "研究部分完成"
    )
    assert events[0].details == {"round": 2, "tasks_json": '["补充论文"]'}
    assert not any(event.event_type == "planning.completed" for event in events)
