import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from types import SimpleNamespace

import pytest

from deeptrace.application.result import ApplicationRunResult
from deeptrace.domain import ResearchOutcome, ResponseOutcome
from deeptrace.runtime.local import LocalResearchRuntime
from deeptrace.runtime.models import RunRecord


class FakeContext:
    workspace_id = "workspace-1"
    evidence_store = object()  # Adapter must not query sources a second time.


class FakeApplication:
    """Application-service stub for runtime lifecycle tests."""

    def __init__(self, *, invoke_hook: Any = None, partial: bool = False) -> None:
        self.requests: list[Any] = []
        self._invoke_hook = invoke_hook
        self.partial = partial

    async def invoke(self, request, *, config, context):
        self.requests.append((request, config, context))
        if self._invoke_hook is not None:
            await self._invoke_hook()
        reason = "max_iterations" if self.partial else "completed"
        gaps = ["Missing comparison"] if self.partial else []
        return ApplicationRunResult(
            run_id=request.run_id,
            thread_id=request.thread_id,
            status="partial" if self.partial else "completed",
            response_outcome=ResponseOutcome(
                response_mode="answer",
                content="简洁回答 [1]",
                citations=[{"evidence_id": "evidence-1", "marker": "[1]"}],
                cited_evidence_ids=["evidence-1"],
            ),
            research_outcome=ResearchOutcome(
                mode="workflow",
                executed_steps=7,
                termination_reason=reason,
                unresolved_gaps=gaps,
            ),
            executed_steps=7,
            termination_reason=reason,
            unresolved_gaps=gaps,
            sources=["https://example.com/a"],
        )


async def wait_for_terminal(runtime: LocalResearchRuntime, run_id: str):
    for _ in range(1000):
        run = await runtime.get(run_id)
        if run is not None and run.status in {"completed", "partial", "failed", "cancelled"}:
            return run
        await asyncio.sleep(0.01)
    raise AssertionError("local run did not reach a terminal state")


def build_runtime(tmp_path, application: FakeApplication) -> LocalResearchRuntime:
    return LocalResearchRuntime(
        object(),
        tmp_path,
        application=application,
        context_factory=lambda run_id, on_event=None: FakeContext(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status,reason", [("failed", "model_error"), ("cancelled", "cancelled")])
async def test_local_terminal_failure_preserves_reason_without_an_answer(tmp_path, status, reason):
    class TerminalApplication:
        async def invoke(self, request, **kwargs):
            return ApplicationRunResult(run_id=request.run_id, thread_id=request.thread_id,
                status=status, termination_reason=reason, executed_steps=0,
                research_outcome=None, response_outcome=None)

    runtime = build_runtime(tmp_path, TerminalApplication())
    await runtime.start()
    try:
        created = await runtime.create("Question", "workflow")
        result = await wait_for_terminal(runtime, created.id)
        assert result.status == status
        assert result.termination_reason == reason
        persisted = json.loads((tmp_path / f"{created.id}.json").read_text("utf-8"))
        assert persisted["finish_reason"] == reason
        assert persisted["research_sufficiency"] == "unknown"
        assert persisted["answer"] == ""
        assert persisted["events"][-1]["message"] == {"failed": "研究失败", "cancelled": "研究已取消"}[status]
    finally:
        await runtime.stop()


def test_historical_record_normalizes_reason_without_rewriting_detail():
    original = dict(id="old", question="Question", created_at=datetime.now(UTC),
                    status="partial", termination_reason="max_iterations")
    result = RunRecord.model_validate(original)
    assert result.model_dump(mode="json")["finish_reason"] == "iteration_limit"
    assert result.research_sufficiency == "unknown"
    assert result.termination_reason == "max_iterations"
    assert RunRecord.model_validate(result.model_dump()).finish_reason == "iteration_limit"


@pytest.mark.asyncio
async def test_local_runtime_persists_actual_model_usage(tmp_path):
    from harness.test_durable_model_budget import Provider, call
    from deeptrace.harness.model_budget import RunBudgetModelGateway

    model = RunBudgetModelGateway(Provider())
    async def invoke_model():
        await call(model)

    runtime = LocalResearchRuntime(object(), tmp_path,
        application=FakeApplication(invoke_hook=invoke_model),
        context_factory=lambda *args: SimpleNamespace(model_gateway=model))
    await runtime.start()
    try:
        created = await runtime.create('question', 'workflow')
        result = await wait_for_terminal(runtime, created.id)
        assert result.usage['total_tokens'] == 82
        assert result.usage['role_usage']['researcher']['input_tokens'] == 70
        persisted = json.loads((tmp_path / f'{created.id}.json').read_text('utf-8'))
        assert persisted['usage']['output_tokens'] == 12
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_preserves_planning_and_tool_failure_details(tmp_path):
    def context_factory(run_id, on_event):
        on_event("tool.completed", {"tool": "fetch_page", "call_id": "fetch-1", "ok": False,
                                   "error_code": "browser_failed", "message": "浏览器超时", "api_key": "secret"})
        on_event("replanning.completed", {"round": 2, "tasks_json": '["论文原文"]'})
        return FakeContext()

    runtime = LocalResearchRuntime(object(), tmp_path, application=FakeApplication(), context_factory=context_factory)
    await runtime.start()
    try:
        created = await runtime.create("研究问题", "plan_execute")
        run = await wait_for_terminal(runtime, created.id)
        assert run.events[0]["details"]["message"] == "浏览器超时"
        assert run.events[0]["details"]["ok"] is False
        assert "api_key" not in run.events[0]["details"]
        assert run.events[1]["details"] == {"round": 2, "tasks_json": '["论文原文"]'}
    finally:
        await runtime.stop()


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
async def test_local_runtime_preserves_partial_research_in_persisted_record(
    tmp_path,
) -> None:
    runtime = build_runtime(tmp_path, FakeApplication(partial=True))
    await runtime.start()
    try:
        created = await runtime.create("Question", "workflow")
        completed = await wait_for_terminal(runtime, created.id)
        assert completed.status == "partial"
        assert completed.termination_reason == "max_iterations"
        assert completed.unresolved_gaps == ["Missing comparison"]
        assert completed.sources == ["https://example.com/a"]
        persisted = json.loads((tmp_path / f"{created.id}.json").read_text("utf-8"))
        assert persisted["status"] == "partial"
        assert persisted["events"][-1]["message"] == "研究部分完成"
    finally:
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
async def test_local_runtime_reloads_history_after_restart(tmp_path) -> None:
    runtime = build_runtime(tmp_path, FakeApplication())
    await runtime.start()
    created = await runtime.create("历史问题", "workflow")
    await wait_for_terminal(runtime, created.id)
    await runtime.stop()

    restarted = build_runtime(tmp_path, FakeApplication())
    await restarted.start()
    try:
        runs = await restarted.list()
        assert [run.id for run in runs] == [created.id]
        reloaded = await restarted.get(created.id)
        assert reloaded is not None
        assert reloaded.status == "completed"
        assert reloaded.answer == "简洁回答 [1]"
        assert reloaded.thread_id == created.thread_id
        # SSE replay for a historical run terminates on the rebuilt done event
        events = [event async for event in restarted.events(created.id)]
        assert events[-1].event_type == "done"
    finally:
        await restarted.stop()


@pytest.mark.asyncio
async def test_local_runtime_marks_interrupted_run_failed_on_restart(tmp_path) -> None:
    record = RunRecord(
        id="interrupted1",
        question="中途断开的研究",
        mode="workflow",
        status="running",
        thread_id="thread-interrupted",
        created_at=datetime(2026, 9, 15, tzinfo=UTC),
    )
    (tmp_path / f"{record.id}.json").write_text(
        record.model_dump_json(), encoding="utf-8"
    )

    runtime = build_runtime(tmp_path, FakeApplication())
    await runtime.start()
    try:
        reloaded = await runtime.get("interrupted1")
        assert reloaded is not None
        assert reloaded.status == "failed"
        assert reloaded.termination_reason == "interrupted"
        assert reloaded.error
    finally:
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
    await wait_for_terminal(runtime, first.id)
    second = await runtime.create("第二轮", "workflow", thread_id=first.thread_id)
    await wait_for_terminal(runtime, second.id)

    request, config, _context = application.requests[1]
    assert request.thread_id == first.thread_id
    assert config["configurable"]["thread_id"] == first.thread_id
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_deletes_terminal_run(tmp_path) -> None:
    runtime = build_runtime(tmp_path, FakeApplication())
    await runtime.start()
    created = await runtime.create("研究问题", "workflow")
    await wait_for_terminal(runtime, created.id)

    assert await runtime.delete(created.id) is True
    assert await runtime.get(created.id) is None
    assert not (tmp_path / f"{created.id}.json").exists()
    assert [run.id for run in await runtime.list()] == []
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_delete_rejects_active_and_missing(tmp_path) -> None:
    from deeptrace.runtime.errors import RunActiveError

    started = asyncio.Event()
    release = asyncio.Event()

    async def hook() -> None:
        started.set()
        await release.wait()

    runtime = build_runtime(tmp_path, FakeApplication(invoke_hook=hook))
    await runtime.start()
    assert await runtime.delete("missing") is False

    run = await runtime.create("研究问题", "workflow")
    await started.wait()
    with pytest.raises(RunActiveError):
        await runtime.delete(run.id)

    release.set()
    await wait_for_terminal(runtime, run.id)
    assert await runtime.delete(run.id) is True
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_rejects_concurrent_runs_on_same_thread(tmp_path) -> None:
    from deeptrace.runtime.errors import ThreadBusyError

    started = asyncio.Event()
    release = asyncio.Event()

    async def hook() -> None:
        started.set()
        await release.wait()

    runtime = build_runtime(tmp_path, FakeApplication(invoke_hook=hook))
    await runtime.start()
    first = await runtime.create("第一轮", "workflow", thread_id="thread-shared")
    await started.wait()

    with pytest.raises(ThreadBusyError):
        await runtime.create("第二轮", "workflow", thread_id="thread-shared")

    release.set()
    await wait_for_terminal(runtime, first.id)
    # the lock releases on completion: the next run on the same thread succeeds
    third = await runtime.create("第三轮", "workflow", thread_id="thread-shared")
    await wait_for_terminal(runtime, third.id)
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_reload_keeps_auto_selection_and_durable_routing_event(tmp_path):
    def factory(run_id, on_event):
        on_event("research.routed", {"mode": "workflow", "reason": "Focused task", "action": "automatic"})
        return FakeContext()

    runtime = LocalResearchRuntime(object(), tmp_path, application=FakeApplication(), context_factory=factory)
    await runtime.start()
    try:
        created = await runtime.create("question", "auto")
        await wait_for_terminal(runtime, created.id)
    finally:
        await runtime.stop()
    restarted = build_runtime(tmp_path, FakeApplication())
    await restarted.start()
    try:
        loaded = await restarted.get(created.id)
        assert loaded.mode == "auto"
        assert loaded.routing_metadata() == {"selected_mode": "workflow", "routing_reason": "Focused task"}
    finally:
        await restarted.stop()
