"""Redis Streams implementation of research job delivery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.exceptions import ResponseError

from deeptrace.runtime.models import JobMessage, StoredEvent


class RedisResearchBroker:
    def __init__(
        self,
        redis,
        *,
        stream: str = "deeptrace:research:jobs",
        group: str = "research-workers",
        consumer: str = "worker-1",
        cancel_ttl_seconds: int = 86_400,
        claim_idle_ms: int = 60_000,
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._cancel_ttl_seconds = cancel_ttl_seconds
        self._claim_idle_ms = claim_idle_ms

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(
                self._stream, self._group, id="0-0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(self, run_id: str) -> str:
        return await self._redis.xadd(self._stream, {"run_id": run_id})

    async def read(self, *, block_ms: int = 5_000) -> list[JobMessage]:
        response = await self._redis.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=1,
            block=block_ms,
        )
        for _, messages in response:
            return await self._decode_messages(messages)
        return []

    async def reclaim_stale(self) -> list[JobMessage]:
        response = await self._redis.xautoclaim(
            self._stream,
            self._group,
            self._consumer,
            self._claim_idle_ms,
            "0-0",
            count=100,
        )
        messages = response[1]
        return await self._decode_messages(messages)

    async def ack(self, message_id: str) -> None:
        await self._redis.xack(self._stream, self._group, message_id)

    async def _decode_messages(self, messages) -> list[JobMessage]:
        jobs: list[JobMessage] = []
        for message_id, fields in messages:
            run_id = fields.get("run_id")
            if not run_id:
                await self.ack(message_id)
                continue
            jobs.append(JobMessage(message_id=message_id, run_id=run_id))
        return jobs

    async def request_cancel(self, run_id: str) -> None:
        await self._redis.set(
            self._cancel_key(run_id), "1", ex=self._cancel_ttl_seconds
        )

    async def is_cancel_requested(self, run_id: str) -> bool:
        return bool(await self._redis.exists(self._cancel_key(run_id)))

    async def clear_cancel(self, run_id: str) -> None:
        await self._redis.delete(self._cancel_key(run_id))

    @staticmethod
    def _cancel_key(run_id: str) -> str:
        return f"deeptrace:research:cancel:{run_id}"

    async def publish_event(self, event: StoredEvent) -> None:
        await self._redis.publish(self._event_channel(event.run_id), str(event.id))

    @asynccontextmanager
    async def subscription(self, run_id: str):
        pubsub = self._redis.pubsub()
        channel = self._event_channel(run_id)
        await pubsub.subscribe(channel)

        async def notifications() -> AsyncIterator[int]:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message is None:
                    await asyncio.sleep(0.01)
                    continue
                yield int(message["data"])

        try:
            yield notifications()
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    @staticmethod
    def _event_channel(run_id: str) -> str:
        return f"deeptrace:research:events:{run_id}"

    async def aclose(self) -> None:
        await self._redis.aclose()
