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
        ("failed", "model_error", []),
        ("cancelled", "cancelled", []),
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
                ) if status in {"completed", "partial"} else None,
                termination_reason=reason,
                executed_steps=7,
                unresolved_gaps=gaps,
                sources=["https://example.com/source"],
                research_sufficiency="insufficient" if gaps else "unknown",
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
    assert result.answer == ("Answer [1]" if status in {"completed", "partial"} else "")
    assert result.finish_reason == {"max_iterations": "iteration_limit"}.get(reason, reason)
    assert result.research_sufficiency == ("insufficient" if gaps else "unknown")
    assert events[-1].message == {
        "completed": "研究已完成", "partial": "研究部分完成",
        "failed": "研究失败", "cancelled": "研究已取消",
    }[status]
    assert events[0].details == {"round": 2, "tasks_json": '["补充论文"]'}
    assert not any(event.event_type == "planning.completed" for event in events)


@pytest.mark.asyncio
async def test_worker_exposes_measured_model_usage_and_releases_run_resources():
    from harness.test_durable_model_budget import Provider, call

    from deeptrace.harness.model_budget import RunBudgetModelGateway

    model = RunBudgetModelGateway(Provider())
    released = []

    class Application:
        async def invoke(self, request, *, config, context):
            await call(context.model_gateway)
            return SimpleNamespace(status='completed', sources=[], executed_steps=0,
                                   termination_reason='completed', unresolved_gaps=[],
                                   research_sufficiency='unknown',
                                   response_outcome=SimpleNamespace(content='answer'))

    runner = HarnessResearchRunner(object())
    runner._bundle = SimpleNamespace(service=Application(),
        context_factory=lambda *args: SimpleNamespace(model_gateway=model),
        release_run=released.append)
    result = await runner(RunRecord(id='run-1', question='question', mode='workflow',
                                   created_at=datetime.now(UTC)))
    assert result.provider_usage.input_tokens == 70
    assert result.provider_usage.output_tokens == 12
    assert result.role_usage.researcher.total_tokens == 82
    assert result.stage_seconds['researcher'] >= 0
    assert result.usage_observation['usage_complete']
    assert released == ['run-1']


@pytest.mark.asyncio
async def test_failed_worker_run_keeps_usage_and_releases_resources():
    from harness.test_durable_model_budget import Provider, call

    from deeptrace.harness.model_budget import RunBudgetModelGateway
    model, released = RunBudgetModelGateway(Provider()), []
    class Application:
        async def invoke(self, request, *, config, context):
            await call(context.model_gateway)
            raise RuntimeError('research failed')
    runner = HarnessResearchRunner(object())
    runner._bundle = SimpleNamespace(service=Application(),
        context_factory=lambda *args: SimpleNamespace(model_gateway=model),
        release_run=released.append)
    run = RunRecord(id='run-1', question='question', created_at=datetime.now(UTC))
    with pytest.raises(RuntimeError, match='research failed'):
        await runner(run)
    assert run.usage['total_tokens'] == 82
    assert released == ['run-1']


@pytest.mark.asyncio
async def test_worker_releases_run_when_context_creation_fails():
    released = []
    def context_factory(*args):
        raise RuntimeError('invalid configuration')
    runner = HarnessResearchRunner(object())
    runner._bundle = SimpleNamespace(context_factory=context_factory, release_run=released.append)
    with pytest.raises(RuntimeError, match='invalid configuration'):
        await runner(RunRecord(id='run-1', question='question', created_at=datetime.now(UTC)))
    assert released == ['run-1']
