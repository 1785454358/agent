from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
import pytest_asyncio

from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.orm import Base
from deeptrace.persistence.repository import SqlAlchemyRunRepository
from deeptrace.models import RunEvent
from deeptrace.queue.redis_streams import RedisResearchBroker
from deeptrace.runtime.distributed import DistributedResearchRuntime, JobDispatchError
from deeptrace.runtime.models import JobMessage


@pytest_asyncio.fixture
async def infrastructure():
    engine, sessions = create_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SqlAlchemyRunRepository(sessions)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    broker = RedisResearchBroker(redis, stream="jobs", group="workers")
    yield repository, broker, redis
    await redis.aclose()
    await engine.dispose()


@pytest.mark.asyncio
async def test_distributed_runtime_persists_then_enqueues_without_agent(
    infrastructure,
) -> None:
    repository, broker, _ = infrastructure
    runtime = DistributedResearchRuntime(
        repository, broker, id_factory=lambda: "run-1"
    )
    await runtime.start()

    created = await runtime.create(" 研究问题 ", "deep")
    persisted = await repository.get("run-1")
    jobs = await broker.read(block_ms=1)

    assert created.id == "run-1"
    assert created.status == "pending"
    assert persisted is not None
    assert persisted.question == "研究问题"
    assert persisted.mode == "deep"
    assert persisted.created_at <= datetime.now(UTC)
    assert jobs == [JobMessage(message_id=jobs[0].message_id, run_id="run-1")]


@pytest.mark.asyncio
async def test_distributed_runtime_reads_runs_and_event_snapshot(
    infrastructure,
) -> None:
    repository, broker, _ = infrastructure
    runtime = DistributedResearchRuntime(
        repository, broker, id_factory=lambda: "run-1"
    )
    await runtime.start()
    await runtime.create("研究问题", "basic")
    await repository.append_event(
        "run-1", RunEvent(event_type="planning.started", message="开始规划")
    )

    loaded = await runtime.get("run-1")
    runs = await runtime.list()

    assert loaded is not None
    assert loaded.events[0]["event_type"] == "planning.started"
    assert loaded.events[0]["message"] == "开始规划"
    assert [run.id for run in runs] == ["run-1"]
    assert await runtime.get("missing") is None


@pytest.mark.asyncio
async def test_distributed_runtime_cancels_active_run_in_database_and_redis(
    infrastructure,
) -> None:
    repository, broker, _ = infrastructure
    runtime = DistributedResearchRuntime(
        repository, broker, id_factory=lambda: "run-1"
    )
    await runtime.start()
    await runtime.create("研究问题", "basic")

    cancelled = await runtime.cancel("run-1")

    assert cancelled is not None
    assert cancelled.status == "cancel_requested"
    assert await broker.is_cancel_requested("run-1") is True
    assert await runtime.cancel("missing") is None


@pytest.mark.asyncio
async def test_dispatch_failure_keeps_pending_run_for_recovery(infrastructure) -> None:
    repository, _, _ = infrastructure

    class FailingBroker:
        async def enqueue(self, run_id: str) -> str:
            raise ConnectionError("redis unavailable")

    runtime = DistributedResearchRuntime(
        repository, FailingBroker(), id_factory=lambda: "run-1"
    )

    with pytest.raises(JobDispatchError, match="run-1"):
        await runtime.create("研究问题", "basic")

    persisted = await repository.get("run-1")
    assert persisted is not None
    assert persisted.status == "pending"


@pytest.mark.asyncio
async def test_distributed_runtime_replays_events_after_cursor(infrastructure) -> None:
    repository, broker, _ = infrastructure
    runtime = DistributedResearchRuntime(
        repository, broker, id_factory=lambda: "run-1"
    )
    await runtime.start()
    await runtime.create("研究问题", "basic")
    first = await repository.append_event(
        "run-1", RunEvent(event_type="planning.started", message="开始")
    )
    second = await repository.append_event(
        "run-1", RunEvent(event_type="planning.completed", message="完成")
    )
    await repository.append_event(
        "run-1", RunEvent(event_type="done", message="")
    )

    events = [event async for event in runtime.events("run-1", first.id)]

    assert [event.event_type for event in events] == ["planning.completed", "done"]
    assert events[0].id == second.id
