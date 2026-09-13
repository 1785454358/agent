import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from deeptrace.models import AgentResult, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.orm import Base
from deeptrace.persistence.repository import SqlAlchemyRunRepository
from deeptrace.runtime.models import JobMessage, RunRecord
from deeptrace.worker.service import ResearchWorker


@pytest_asyncio.fixture
async def repository():
    engine, sessions = create_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield SqlAlchemyRunRepository(sessions)
    await engine.dispose()


class RecordingBroker:
    def __init__(self) -> None:
        self.published = []
        self.acked = []
        self.cancelled = set()
        self.closed = False
        self.enqueued = []

    async def enqueue(self, run_id: str) -> str:
        self.enqueued.append(run_id)
        return f"message-{len(self.enqueued)}"

    async def publish_event(self, event) -> None:
        self.published.append(event)

    async def ack(self, message_id: str) -> None:
        self.acked.append(message_id)

    async def is_cancel_requested(self, run_id: str) -> bool:
        return run_id in self.cancelled

    async def clear_cancel(self, run_id: str) -> None:
        self.cancelled.discard(run_id)

    async def aclose(self) -> None:
        self.closed = True


class EventfulAgent:
    def __init__(self, on_event) -> None:
        self.on_event = on_event
        self.closed = False

    async def arun(self, question: str) -> AgentResult:
        self.on_event(RunEvent(event_type="planning.completed", message="规划完成"))
        return AgentResult(
            status="completed",
            answer=f"报告：{question}",
            sources=["https://example.com/a"],
            steps=2,
            events=[],
            termination_reason="completed",
            search_queries=[question],
            provider_usage=TokenUsage(total_tokens=12),
            role_usage=UsageBreakdown(),
            estimated_cost_usd=None,
            stage_seconds={"writer": 0.1},
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_worker_persists_result_and_events_before_ack(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    broker = RecordingBroker()
    agents = []

    def factory(settings, on_event=None, mode="basic"):
        agent = EventfulAgent(on_event)
        agents.append(agent)
        return agent

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
    )

    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))

    run = await repository.get("run-1")
    events = await repository.events_after("run-1", 0)
    assert run is not None
    assert run.status == "completed"
    assert run.answer == "报告：研究问题"
    assert [event.event_type for event in events] == ["planning.completed", "done"]
    assert [event.id for event in broker.published] == [event.id for event in events]
    assert broker.acked == ["1-0"]
    assert agents[0].closed is True


@pytest.mark.asyncio
async def test_worker_acks_terminal_duplicate_without_running_agent(repository) -> None:
    await repository.create(
        RunRecord(
            id="run-1",
            question="研究问题",
            status="completed",
            created_at=datetime.now(UTC),
        )
    )
    broker = RecordingBroker()
    constructed = []

    def factory(*args, **kwargs):
        constructed.append(True)
        return EventfulAgent(kwargs["on_event"])

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
    )

    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))

    assert constructed == []
    assert broker.acked == ["1-0"]


@pytest.mark.asyncio
async def test_worker_finishes_pre_cancelled_job_without_agent(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    await repository.request_cancel("run-1")
    broker = RecordingBroker()
    broker.cancelled.add("run-1")
    constructed = []

    def factory(*args, **kwargs):
        constructed.append(True)
        return EventfulAgent(kwargs["on_event"])

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
    )

    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))

    run = await repository.get("run-1")
    events = await repository.events_after("run-1", 0)
    assert constructed == []
    assert run is not None
    assert run.status == "cancelled"
    assert [event.event_type for event in events] == ["done"]
    assert broker.acked == ["1-0"]
    assert broker.cancelled == set()


@pytest.mark.asyncio
async def test_worker_persists_sanitized_agent_construction_failure(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    broker = RecordingBroker()

    def broken_factory(*args, **kwargs):
        raise ValueError("provider failed with secret-test-key")

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=broken_factory,
        worker_id="worker-1",
    )

    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))

    run = await repository.get("run-1")
    assert run is not None
    assert run.status == "failed"
    assert run.error == "运行失败（ValueError），请检查服务与模型配置"
    assert "secret-test-key" not in run.model_dump_json()
    assert broker.acked == ["1-0"]


@pytest.mark.asyncio
async def test_worker_drains_events_and_closes_agent_on_execution_failure(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    broker = RecordingBroker()

    class FailingAgent(EventfulAgent):
        async def arun(self, question: str) -> AgentResult:
            self.on_event(
                RunEvent(event_type="planning.completed", message="规划已持久化")
            )
            raise RuntimeError("upstream leaked secret-test-key")

    agent = None

    def factory(settings, on_event=None, mode="basic"):
        nonlocal agent
        agent = FailingAgent(on_event)
        return agent

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
    )

    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))

    run = await repository.get("run-1")
    events = await repository.events_after("run-1", 0)
    assert run is not None
    assert run.status == "failed"
    assert run.error == "运行失败（RuntimeError），请检查服务与模型配置"
    assert [event.event_type for event in events] == ["planning.completed", "done"]
    assert agent is not None and agent.closed is True
    assert broker.acked == ["1-0"]


@pytest.mark.asyncio
async def test_worker_cancels_running_agent_when_cancel_is_requested(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    broker = RecordingBroker()
    started = asyncio.Event()

    class BlockingAgent(EventfulAgent):
        async def arun(self, question: str) -> AgentResult:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    agent = None

    def factory(settings, on_event=None, mode="basic"):
        nonlocal agent
        agent = BlockingAgent(on_event)
        return agent

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
        heartbeat_interval_seconds=0.01,
    )
    processing = asyncio.create_task(
        worker.process(JobMessage(message_id="1-0", run_id="run-1"))
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    broker.cancelled.add("run-1")
    await asyncio.wait_for(processing, timeout=1)

    run = await repository.get("run-1")
    assert run is not None
    assert run.status == "cancelled"
    assert agent is not None and agent.closed is True
    assert broker.acked == ["1-0"]
    assert broker.cancelled == set()


@pytest.mark.asyncio
async def test_worker_fails_job_after_max_attempts_without_running_agent(repository) -> None:
    await repository.create(
        RunRecord(
            id="run-1",
            question="研究问题",
            attempt_count=3,
            created_at=datetime.now(UTC),
        )
    )
    broker = RecordingBroker()
    constructed = []

    def factory(*args, **kwargs):
        constructed.append(True)
        return EventfulAgent(kwargs["on_event"])

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
    )

    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))

    run = await repository.get("run-1")
    assert run is not None
    assert run.status == "failed"
    assert run.error == "任务超过最大重试次数（3）"
    assert constructed == []
    assert broker.acked == ["1-0"]


@pytest.mark.asyncio
async def test_run_forever_reclaims_stale_jobs_before_reading_new_ones(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="恢复任务", created_at=datetime.now(UTC))
    )

    class LoopBroker(RecordingBroker):
        def __init__(self) -> None:
            super().__init__()
            self.calls = []
            self.read_started = asyncio.Event()

        async def ensure_group(self) -> None:
            self.calls.append("ensure_group")

        async def reclaim_stale(self) -> list[JobMessage]:
            self.calls.append("reclaim_stale")
            return [JobMessage(message_id="stale-0", run_id="run-1")]

        async def read(self, *, block_ms: int = 5_000) -> list[JobMessage]:
            self.calls.append("read")
            self.read_started.set()
            await asyncio.Event().wait()
            return []

    broker = LoopBroker()
    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=lambda settings, on_event=None, mode="basic": EventfulAgent(
            on_event
        ),
        worker_id="worker-1",
    )

    loop_task = asyncio.create_task(worker.run_forever())
    await asyncio.wait_for(broker.read_started.wait(), timeout=1)
    loop_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop_task

    run = await repository.get("run-1")
    assert run is not None and run.status == "completed"
    assert broker.calls[:3] == ["ensure_group", "reclaim_stale", "read"]
    assert broker.acked == ["stale-0"]


@pytest.mark.asyncio
async def test_worker_cancellation_stops_agent_and_monitor_without_ack(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    broker = RecordingBroker()
    started = asyncio.Event()

    class CancellableAgent(EventfulAgent):
        def __init__(self, on_event) -> None:
            super().__init__(on_event)
            self.cancelled = False

        async def arun(self, question: str) -> AgentResult:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    agent = None

    def factory(settings, on_event=None, mode="basic"):
        nonlocal agent
        agent = CancellableAgent(on_event)
        return agent

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
        heartbeat_interval_seconds=0.01,
    )
    processing = asyncio.create_task(
        worker.process(JobMessage(message_id="1-0", run_id="run-1"))
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    processing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await processing
    await asyncio.sleep(0)

    assert agent is not None
    assert agent.cancelled is True
    assert agent.closed is True
    assert broker.acked == []


@pytest.mark.asyncio
async def test_worker_stops_stale_agent_without_terminal_write_or_ack(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    repository.renew_lease = AsyncMock(return_value=False)
    broker = RecordingBroker()
    started = asyncio.Event()

    class BlockingAgent(EventfulAgent):
        async def arun(self, question: str) -> AgentResult:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    agent = None

    def factory(settings, on_event=None, mode="basic"):
        nonlocal agent
        agent = BlockingAgent(on_event)
        return agent

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
        heartbeat_interval_seconds=0.01,
    )
    await asyncio.wait_for(
        worker.process(JobMessage(message_id="1-0", run_id="run-1")), timeout=1
    )

    run = await repository.get("run-1")
    assert run is not None and run.status == "running"
    assert agent is not None and agent.closed is True
    assert broker.acked == []


@pytest.mark.asyncio
async def test_worker_does_not_ack_when_result_fencing_write_fails(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    repository.complete = AsyncMock(return_value=None)
    broker = RecordingBroker()
    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=lambda settings, on_event=None, mode="basic": EventfulAgent(
            on_event
        ),
        worker_id="worker-1",
    )

    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))

    assert broker.acked == []


@pytest.mark.asyncio
async def test_worker_requeues_stale_and_expired_database_runs(repository) -> None:
    now = datetime.now(UTC)
    await repository.create(
        RunRecord(
            id="stale-pending",
            question="问题",
            created_at=now - timedelta(minutes=5),
        )
    )
    await repository.create(
        RunRecord(
            id="expired-running",
            question="问题",
            status="running",
            created_at=now - timedelta(minutes=5),
            lease_owner="dead-worker",
            lease_expires_at=now - timedelta(seconds=1),
        )
    )
    broker = RecordingBroker()
    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=lambda *args, **kwargs: None,
        worker_id="worker-1",
    )

    await worker.recover_stale(older_than_seconds=60)

    assert set(broker.enqueued) == {"stale-pending", "expired-running"}


@pytest.mark.asyncio
async def test_worker_stops_agent_when_redis_monitor_fails(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    started = asyncio.Event()

    class BrokenMonitorBroker(RecordingBroker):
        async def is_cancel_requested(self, run_id: str) -> bool:
            if started.is_set():
                raise ConnectionError("redis password secret-test-key")
            return False

    class BlockingAgent(EventfulAgent):
        def __init__(self, on_event) -> None:
            super().__init__(on_event)
            self.cancelled = False

        async def arun(self, question: str) -> AgentResult:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    broker = BrokenMonitorBroker()
    agent = None

    def factory(settings, on_event=None, mode="basic"):
        nonlocal agent
        agent = BlockingAgent(on_event)
        return agent

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=factory,
        worker_id="worker-1",
        heartbeat_interval_seconds=0.01,
    )

    await asyncio.wait_for(
        worker.process(JobMessage(message_id="1-0", run_id="run-1")), timeout=1
    )

    run = await repository.get("run-1")
    assert run is not None
    assert run.status == "failed"
    assert run.error == "运行失败（ConnectionError），请检查服务与模型配置"
    assert "secret-test-key" not in run.model_dump_json()
    assert agent is not None and agent.cancelled is True and agent.closed is True
    assert broker.acked == ["1-0"]


@pytest.mark.asyncio
async def test_worker_drains_events_and_fails_when_agent_close_fails(repository) -> None:
    await repository.create(
        RunRecord(id="run-1", question="研究问题", created_at=datetime.now(UTC))
    )
    broker = RecordingBroker()

    class BrokenCloseAgent(EventfulAgent):
        async def aclose(self) -> None:
            raise OSError("close leaked secret-test-key")

    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=lambda settings, on_event=None, mode="basic": BrokenCloseAgent(
            on_event
        ),
        worker_id="worker-1",
    )

    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))

    run = await repository.get("run-1")
    events = await repository.events_after("run-1", 0)
    assert run is not None and run.status == "failed"
    assert run.error == "运行失败（OSError），请检查服务与模型配置"
    assert [event.event_type for event in events] == ["planning.completed", "done"]
    assert broker.acked == ["1-0"]


@pytest.mark.asyncio
async def test_worker_runner_receives_database_run_identity(repository) -> None:
    """The runner path must see the persisted run id and thread id."""
    await repository.create(
        RunRecord(
            id="run-runner",
            thread_id="thread-runner",
            question="研究问题",
            created_at=datetime.now(UTC),
        )
    )
    seen: list[RunRecord] = []

    async def runner(run: RunRecord, on_event=None):
        seen.append(run)
        return AgentResult(
            status="completed",
            answer="runner 回答",
            sources=[],
            steps=1,
            events=[],
            termination_reason="completed",
            search_queries=[],
            provider_usage=TokenUsage(),
            role_usage=UsageBreakdown(),
            estimated_cost_usd=None,
            stage_seconds={},
        )

    worker = ResearchWorker(
        repository,
        RecordingBroker(),
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        research_runner=runner,
        worker_id="worker-1",
    )
    await worker.process(JobMessage(message_id="9-0", run_id="run-runner"))

    run = await repository.get("run-runner")
    assert run is not None
    assert run.status == "completed"
    assert run.answer == "runner 回答"
    assert seen and seen[0].id == "run-runner"
    assert seen[0].thread_id == "thread-runner"
