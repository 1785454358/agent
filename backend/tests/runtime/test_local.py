import asyncio
import json

import pytest

from deeptrace.models import AgentResult, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.runtime.local import LocalResearchRuntime


class FakeAgent:
    def __init__(self, on_event) -> None:
        self._on_event = on_event

    async def arun(self, question: str) -> AgentResult:
        self._on_event(
            RunEvent(event_type="planning.completed", message=f"已规划：{question}")
        )
        return AgentResult(
            status="completed",
            answer="报告正文",
            sources=["https://example.com/a"],
            steps=2,
            events=[],
            termination_reason="completed",
            search_queries=[question],
            provider_usage=TokenUsage(total_tokens=21),
            role_usage=UsageBreakdown(),
            estimated_cost_usd=None,
            stage_seconds={"writer": 0.2},
        )

    async def aclose(self) -> None:
        return None


def fake_agent_factory(settings, on_event=None, mode="basic") -> FakeAgent:
    return FakeAgent(on_event)


async def wait_for_terminal(runtime: LocalResearchRuntime, run_id: str):
    for _ in range(100):
        run = await runtime.get(run_id)
        if run is not None and run.status in {"completed", "partial", "failed"}:
            return run
        await asyncio.sleep(0.01)
    raise AssertionError("local run did not reach a terminal state")


@pytest.mark.asyncio
async def test_local_runtime_executes_and_persists_run(tmp_path) -> None:
    runtime = LocalResearchRuntime(
        settings=object(),
        runs_dir=tmp_path,
        agent_factory=fake_agent_factory,
    )
    await runtime.start()

    created = await runtime.create("研究问题", "basic")
    completed = await wait_for_terminal(runtime, created.id)

    assert completed.status == "completed"
    assert completed.answer == "报告正文"
    assert completed.sources == ["https://example.com/a"]
    assert completed.usage is not None
    assert completed.usage["total_tokens"] == 21
    assert completed.events[0]["event_type"] == "planning.completed"
    persisted = json.loads((tmp_path / f"{created.id}.json").read_text("utf-8"))
    assert persisted["status"] == "completed"
    assert persisted["events"][0]["message"] == "已规划：研究问题"
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_lists_newest_run_first(tmp_path) -> None:
    runtime = LocalResearchRuntime(object(), tmp_path, fake_agent_factory)
    await runtime.start()
    first = await runtime.create("问题一", "basic")
    await asyncio.sleep(0.001)
    second = await runtime.create("问题二", "deep")

    runs = await runtime.list()

    assert [run.id for run in runs] == [second.id, first.id]
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_replays_events_and_finishes_stream(tmp_path) -> None:
    runtime = LocalResearchRuntime(object(), tmp_path, fake_agent_factory)
    await runtime.start()
    run = await runtime.create("研究问题", "basic")
    await wait_for_terminal(runtime, run.id)

    events = [event async for event in runtime.events(run.id)]

    assert [event.event_type for event in events] == [
        "planning.completed",
        "done",
    ]
    assert [event.id for event in events] == sorted(event.id for event in events)
    assert events[0].payload["message"] == "已规划：研究问题"
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_cancels_running_agent_and_closes_it(tmp_path) -> None:
    started = asyncio.Event()
    agent_holder = []

    class BlockingAgent:
        def __init__(self) -> None:
            self.closed = False

        async def arun(self, question: str):
            started.set()
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            self.closed = True

    def factory(settings, on_event=None, mode="basic"):
        agent = BlockingAgent()
        agent_holder.append(agent)
        return agent

    runtime = LocalResearchRuntime(object(), tmp_path, factory)
    await runtime.start()
    run = await runtime.create("研究问题", "basic")
    await started.wait()

    cancelled = await runtime.cancel(run.id)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.termination_reason == "cancelled"
    assert agent_holder[0].closed is True
    persisted = json.loads((tmp_path / f"{run.id}.json").read_text("utf-8"))
    assert persisted["status"] == "cancelled"
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_rejects_blank_question(tmp_path) -> None:
    runtime = LocalResearchRuntime(object(), tmp_path, fake_agent_factory)

    with pytest.raises(ValueError, match="问题不能为空"):
        await runtime.create("   ", "basic")


def test_run_record_normalizes_legacy_modes_on_read() -> None:
    from datetime import UTC, datetime

    from deeptrace.runtime.models import RunRecord

    record = RunRecord.model_validate(
        {
            "id": "run-1",
            "question": "问题",
            "mode": "basic",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    assert record.mode == "workflow"
    record = RunRecord.model_validate(
        {
            "id": "run-2",
            "question": "问题",
            "mode": "deep",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    assert record.mode == "plan_execute"
    with pytest.raises(ValueError):
        RunRecord.model_validate(
            {
                "id": "run-3",
                "question": "问题",
                "mode": "agent",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )


@pytest.mark.asyncio
async def test_local_runtime_runs_through_application_service(tmp_path) -> None:
    from datetime import UTC, datetime

    from deeptrace.application.research import ApplicationResearchRequest
    from deeptrace.domain import ResponseMode

    class FakeOutcome:
        response_mode = ResponseMode.ANSWER
        content = "简洁回答 [1]"
        partial_reason = None
        cited_evidence_ids = ["evidence-1"]

    class FakeEvidence:
        canonical_url = "https://example.com/a"

    class FakeEvidenceStore:
        async def get_many(self, tenant_id, ids):
            return [FakeEvidence() for _ in ids]

    class FakeContext:
        workspace_id = "workspace-1"
        evidence_store = FakeEvidenceStore()

    class FakeApplication:
        def __init__(self) -> None:
            self.requests = []

        async def invoke(self, request, *, config, context):
            self.requests.append((request, config, context))
            return FakeOutcome()

    application = FakeApplication()
    runtime = LocalResearchRuntime(
        object(),
        tmp_path,
        agent_factory=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy path must not run")
        ),
        application=application,
        context_factory=lambda run_id: FakeContext(),
    )
    await runtime.start()

    created = await runtime.create("研究问题", "workflow")
    completed = await wait_for_terminal(runtime, created.id)

    assert completed.status == "completed"
    assert completed.termination_reason == "completed"
    assert completed.answer == "简洁回答 [1]"
    assert completed.sources == ["https://example.com/a"]
    request, config, context = application.requests[0]
    assert isinstance(request, ApplicationResearchRequest)
    assert request.run_id == created.id
    assert request.thread_id == created.id
    assert request.mode == "workflow"
    assert config["configurable"]["thread_id"] == created.id
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_maps_canonical_mode_for_legacy_factory(tmp_path) -> None:
    seen_modes = []

    def factory(settings, on_event=None, mode="basic"):
        seen_modes.append(mode)
        return FakeAgent(on_event)

    runtime = LocalResearchRuntime(object(), tmp_path, factory)
    await runtime.start()
    run = await runtime.create("研究问题", "plan_execute")
    await wait_for_terminal(runtime, run.id)

    assert seen_modes == ["deep"]
    persisted = json.loads((tmp_path / f"{run.id}.json").read_text("utf-8"))
    assert persisted["mode"] == "plan_execute"
    await runtime.stop()
