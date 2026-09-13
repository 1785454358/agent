import asyncio
import json
from typing import Any

import pytest

from deeptrace.domain import ResponseMode
from deeptrace.runtime.local import LocalResearchRuntime


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
    """Application-service stub for runtime lifecycle tests."""

    def __init__(self, *, invoke_hook: Any = None) -> None:
        self.requests: list[Any] = []
        self._invoke_hook = invoke_hook

    async def invoke(self, request, *, config, context):
        self.requests.append((request, config, context))
        if self._invoke_hook is not None:
            await self._invoke_hook()
        return FakeOutcome()


async def wait_for_terminal(runtime: LocalResearchRuntime, run_id: str):
    for _ in range(1000):
        run = await runtime.get(run_id)
        if run is not None and run.status in {"completed", "partial", "failed"}:
            return run
        await asyncio.sleep(0.01)
    raise AssertionError("local run did not reach a terminal state")


def build_runtime(tmp_path, application: FakeApplication) -> LocalResearchRuntime:
    return LocalResearchRuntime(
        object(),
        tmp_path,
        application=application,
        context_factory=lambda run_id: FakeContext(),
    )


@pytest.mark.asyncio
async def test_local_runtime_executes_and_persists_run(tmp_path) -> None:
    runtime = build_runtime(tmp_path, FakeApplication())
    await runtime.start()

    created = await runtime.create("研究问题", "workflow")
    completed = await wait_for_terminal(runtime, created.id)

    assert completed.status == "completed"
    assert completed.answer == "简洁回答 [1]"
    assert completed.sources == ["https://example.com/a"]
    assert completed.thread_id
    assert completed.events[0]["event_type"] == "response.completed"
    persisted = json.loads((tmp_path / f"{created.id}.json").read_text("utf-8"))
    assert persisted["status"] == "completed"
    assert persisted["answer"] == "简洁回答 [1]"
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_lists_newest_run_first(tmp_path) -> None:
    runtime = build_runtime(tmp_path, FakeApplication())
    await runtime.start()
    first = await runtime.create("问题一", "workflow")
    await asyncio.sleep(0.05)
    second = await runtime.create("问题二", "plan_execute")

    runs = await runtime.list()

    assert [run.id for run in runs] == [second.id, first.id]
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_replays_events_and_finishes_stream(tmp_path) -> None:
    runtime = build_runtime(tmp_path, FakeApplication())
    await runtime.start()
    run = await runtime.create("研究问题", "workflow")
    await wait_for_terminal(runtime, run.id)

    events = [event async for event in runtime.events(run.id)]

    assert [event.event_type for event in events] == ["response.completed", "done"]
    assert [event.id for event in events] == sorted(event.id for event in events)
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_cancels_running_research(tmp_path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def hook() -> None:
        started.set()
        await release.wait()

    runtime = build_runtime(tmp_path, FakeApplication(invoke_hook=hook))
    await runtime.start()
    run = await runtime.create("研究问题", "workflow")
    await started.wait()

    cancelled = await runtime.cancel(run.id)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.termination_reason == "cancelled"
    persisted = json.loads((tmp_path / f"{run.id}.json").read_text("utf-8"))
    assert persisted["status"] == "cancelled"
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_rejects_blank_question(tmp_path) -> None:
    runtime = build_runtime(tmp_path, FakeApplication())

    with pytest.raises(ValueError, match="问题不能为空"):
        await runtime.create("   ", "workflow")


@pytest.mark.asyncio
async def test_local_runtime_runs_through_application_service(tmp_path) -> None:
    application = FakeApplication()
    runtime = build_runtime(tmp_path, application)
    await runtime.start()

    created = await runtime.create("研究问题", "workflow")
    completed = await wait_for_terminal(runtime, created.id)

    assert completed.status == "completed"
    assert completed.answer == "简洁回答 [1]"
    assert completed.sources == ["https://example.com/a"]
    request, config, context = application.requests[0]
    assert request.run_id == created.id
    assert request.thread_id == created.thread_id
    assert request.mode == "workflow"
    assert config["configurable"]["thread_id"] == created.thread_id
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_continues_the_requested_thread(tmp_path) -> None:
    application = FakeApplication()
    runtime = build_runtime(tmp_path, application)
    await runtime.start()

    first = await runtime.create("第一轮", "workflow")
    second = await runtime.create("第二轮", "workflow", thread_id=first.thread_id)
    await wait_for_terminal(runtime, second.id)

    request, config, _context = application.requests[1]
    assert request.thread_id == first.thread_id
    assert config["configurable"]["thread_id"] == first.thread_id
    await runtime.stop()
