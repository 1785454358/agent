from types import SimpleNamespace

import fakeredis.aioredis
import pytest

from deeptrace.models import AgentResult, RunEvent, TokenUsage, UsageBreakdown
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.orm import Base
from deeptrace.persistence.repository import SqlAlchemyRunRepository
from deeptrace.queue.redis_streams import RedisResearchBroker
from deeptrace.runtime.distributed import DistributedResearchRuntime
from deeptrace.worker.service import ResearchWorker


class IntegrationAgent:
    def __init__(self, on_event) -> None:
        self._on_event = on_event

    async def arun(self, question: str) -> AgentResult:
        self._on_event(
            RunEvent(event_type="planning.completed", message="集成规划完成")
        )
        self._on_event(
            RunEvent(event_type="writing.completed", message="集成报告完成")
        )
        return AgentResult(
            status="completed",
            answer=f"集成报告：{question}",
            sources=["https://example.com/integration"],
            steps=2,
            events=[],
            termination_reason="completed",
            search_queries=[question],
            provider_usage=TokenUsage(total_tokens=20),
            role_usage=UsageBreakdown(),
            estimated_cost_usd=None,
            stage_seconds={"writer": 0.1},
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_distributed_create_worker_result_and_sse_replay() -> None:
    engine, sessions = create_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SqlAlchemyRunRepository(sessions)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    broker = RedisResearchBroker(
        redis,
        stream="integration:jobs",
        group="integration-workers",
        consumer="worker-1",
        claim_idle_ms=1_000,
    )
    runtime = DistributedResearchRuntime(
        repository,
        broker,
        id_factory=lambda: "run-integration",
    )
    worker = ResearchWorker(
        repository,
        broker,
        SimpleNamespace(worker_lease_seconds=60, worker_max_attempts=3),
        agent_factory=lambda settings, on_event=None, mode="basic": IntegrationAgent(
            on_event
        ),
        worker_id="worker-1",
    )

    try:
        await runtime.start()
        created = await runtime.create("集成研究问题", "multi_agent")
        jobs = await broker.read(block_ms=1)
        assert created.status == "pending"
        assert len(jobs) == 1

        await worker.process(jobs[0])

        completed = await runtime.get(created.id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.answer == "集成报告：集成研究问题"
        assert completed.usage is not None
        assert completed.usage["total_tokens"] == 20

        stored = await repository.events_after(created.id, 0)
        replayed = [
            event async for event in runtime.events(created.id, stored[0].id)
        ]
        assert [event.event_type for event in replayed] == [
            "writing.completed",
            "done",
        ]
        assert replayed[0].id > stored[0].id
    finally:
        await runtime.stop()
        await engine.dispose()
