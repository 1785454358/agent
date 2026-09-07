import fakeredis.aioredis
import pytest
from datetime import UTC, datetime

from deeptrace.queue.redis_streams import RedisResearchBroker
from deeptrace.runtime.models import JobMessage, StoredEvent


@pytest.mark.asyncio
async def test_enqueue_read_and_ack() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    broker = RedisResearchBroker(
        redis,
        stream="jobs",
        group="workers",
        consumer="worker-1",
    )
    await broker.ensure_group()

    message_id = await broker.enqueue("run-1")
    jobs = await broker.read(block_ms=1)

    assert jobs == [JobMessage(message_id=message_id, run_id="run-1")]
    pending = await redis.xpending("jobs", "workers")
    assert pending["pending"] == 1

    await broker.ack(message_id)

    pending = await redis.xpending("jobs", "workers")
    assert pending["pending"] == 0
    await redis.aclose()


@pytest.mark.asyncio
async def test_ensure_group_is_idempotent() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    broker = RedisResearchBroker(redis, stream="jobs", group="workers")

    await broker.ensure_group()
    await broker.ensure_group()

    assert len(await redis.xinfo_groups("jobs")) == 1
    await redis.aclose()


@pytest.mark.asyncio
async def test_cancel_marker_can_be_checked_cleared_and_expires() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    broker = RedisResearchBroker(redis, cancel_ttl_seconds=60)

    await broker.request_cancel("run-1")

    assert await broker.is_cancel_requested("run-1") is True
    ttl = await redis.ttl("deeptrace:research:cancel:run-1")
    assert 0 < ttl <= 60
    await broker.clear_cancel("run-1")
    assert await broker.is_cancel_requested("run-1") is False
    await redis.aclose()


@pytest.mark.asyncio
async def test_event_subscription_receives_only_persisted_event_id() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    broker = RedisResearchBroker(redis)
    event = StoredEvent(
        id=17,
        run_id="run-1",
        event_type="tool.completed",
        payload={"message": "完成"},
        created_at=datetime.now(UTC),
    )

    async with broker.subscription("run-1") as notifications:
        await broker.publish_event(event)
        event_id = await anext(notifications)

    assert event_id == 17
    assert await redis.pubsub_numsub("deeptrace:research:events:run-1") == [
        ("deeptrace:research:events:run-1", 0)
    ]
    await redis.aclose()


@pytest.mark.asyncio
async def test_reclaim_stale_moves_pending_job_to_current_consumer() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    first = RedisResearchBroker(
        redis, stream="jobs", group="workers", consumer="worker-1"
    )
    second = RedisResearchBroker(
        redis,
        stream="jobs",
        group="workers",
        consumer="worker-2",
        claim_idle_ms=0,
    )
    await first.ensure_group()
    message_id = await first.enqueue("run-1")
    assert await first.read(block_ms=1) == [
        JobMessage(message_id=message_id, run_id="run-1")
    ]

    reclaimed = await second.reclaim_stale()

    assert reclaimed == [JobMessage(message_id=message_id, run_id="run-1")]
    pending = await redis.xpending_range("jobs", "workers", "-", "+", 1)
    assert pending[0]["consumer"] == "worker-2"
    await redis.aclose()


@pytest.mark.asyncio
async def test_read_acknowledges_malformed_job_instead_of_crashing() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    broker = RedisResearchBroker(redis, stream="jobs", group="workers")
    await broker.ensure_group()
    await redis.xadd("jobs", {"unexpected": "value"})

    jobs = await broker.read(block_ms=1)

    assert jobs == []
    pending = await redis.xpending("jobs", "workers")
    assert pending["pending"] == 0
    await redis.aclose()
