"""Consume one durable research job and persist its lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from deeptrace import build_real_agent
from deeptrace.config import Settings
from deeptrace.models import RunEvent
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.repository import RunRepository, SqlAlchemyRunRepository
from deeptrace.queue.protocol import ResearchBroker
from deeptrace.queue.redis_streams import RedisResearchBroker
from deeptrace.runtime.models import JobMessage


class ResearchWorker:
    def __init__(
        self,
        repository: RunRepository,
        broker: ResearchBroker,
        settings,
        *,
        agent_factory=build_real_agent,
        worker_id: str,
        heartbeat_interval_seconds: float | None = None,
        close_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._settings = settings
        self._agent_factory = agent_factory
        self._worker_id = worker_id
        self._close_callback = close_callback
        self._heartbeat_interval_seconds = heartbeat_interval_seconds or min(
            1.0, self._settings.worker_lease_seconds / 4
        )

    async def run_forever(self) -> None:
        try:
            await self._broker.ensure_group()
            for job in await self._broker.reclaim_stale():
                await self.process(job)
            await self.recover_stale()
            while True:
                for job in await self._broker.read():
                    await self.process(job)
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        await self._broker.aclose()
        if self._close_callback is not None:
            await self._close_callback()

    async def recover_stale(self, *, older_than_seconds: int = 60) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        for run in await self._repository.recoverable_before(cutoff, limit=100):
            await self._broker.enqueue(run.id)

    async def process(self, job: JobMessage) -> None:
        run = await self._repository.claim(
            job.run_id,
            self._worker_id,
            self._settings.worker_lease_seconds,
        )
        if run is None:
            await self._broker.ack(job.message_id)
            return
        if run.attempt_count > self._settings.worker_max_attempts:
            failed = await self._repository.fail(
                run.id,
                self._worker_id,
                f"任务超过最大重试次数（{self._settings.worker_max_attempts}）",
            )
            if failed is not None:
                await self._append_done_and_ack(run.id, job.message_id)
            return
        if await self._broker.is_cancel_requested(run.id):
            cancelled = await self._repository.cancel(
                run.id, self._worker_id, "运行被用户取消"
            )
            if cancelled is not None:
                await self._append_done_and_ack(run.id, job.message_id)
            return

        event_queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()

        def on_event(event: RunEvent) -> None:
            event_queue.put_nowait(event)

        async def drain_events() -> None:
            while (event := await event_queue.get()) is not None:
                stored = await self._repository.append_event(run.id, event)
                await self._broker.publish_event(stored)

        drain_task = asyncio.create_task(drain_events())
        try:
            agent = self._agent_factory(
                self._settings, on_event=on_event, mode=run.mode
            )
        except Exception as exc:
            event_queue.put_nowait(None)
            await drain_task
            failed = await self._repository.fail(
                run.id,
                self._worker_id,
                f"运行失败（{type(exc).__name__}），请检查服务与模型配置",
            )
            if failed is not None:
                await self._append_done_and_ack(run.id, job.message_id)
            return
        execution_error: Exception | None = None
        control_outcome: str | None = None
        research_task = asyncio.create_task(agent.arun(run.question))
        monitor_task = asyncio.create_task(self._monitor(run.id))
        try:
            done, _ = await asyncio.wait(
                {research_task, monitor_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if research_task in done:
                monitor_task.cancel()
                with suppress(asyncio.CancelledError):
                    await monitor_task
                try:
                    result = research_task.result()
                except Exception as exc:
                    execution_error = exc
            else:
                try:
                    control_outcome = monitor_task.result()
                except Exception as exc:
                    execution_error = exc
                research_task.cancel()
                with suppress(asyncio.CancelledError):
                    await research_task
        except asyncio.CancelledError:
            research_task.cancel()
            monitor_task.cancel()
            await asyncio.gather(
                research_task,
                monitor_task,
                return_exceptions=True,
            )
            raise
        finally:
            try:
                await agent.aclose()
            except Exception as exc:
                if execution_error is None:
                    execution_error = exc
            finally:
                event_queue.put_nowait(None)
                await drain_task

        if control_outcome == "cancelled":
            cancelled = await self._repository.cancel(
                run.id, self._worker_id, "运行被用户取消"
            )
            if cancelled is not None:
                await self._append_done_and_ack(run.id, job.message_id)
            return
        if control_outcome == "lease_lost":
            return

        if execution_error is not None:
            failed = await self._repository.fail(
                run.id,
                self._worker_id,
                f"运行失败（{type(execution_error).__name__}），"
                "请检查服务与模型配置",
            )
            if failed is not None:
                await self._append_done_and_ack(run.id, job.message_id)
            return

        completed = await self._repository.complete(
            run.id, self._worker_id, result
        )
        if completed is None:
            return
        await self._append_done_and_ack(run.id, job.message_id)

    async def _monitor(self, run_id: str) -> str:
        while True:
            await asyncio.sleep(self._heartbeat_interval_seconds)
            if await self._broker.is_cancel_requested(run_id):
                return "cancelled"
            renewed = await self._repository.renew_lease(
                run_id,
                self._worker_id,
                self._settings.worker_lease_seconds,
            )
            if not renewed:
                return "lease_lost"

    async def _append_done_and_ack(self, run_id: str, message_id: str) -> None:
        done = await self._repository.append_event(
            run_id, RunEvent(event_type="done", message="")
        )
        await self._broker.publish_event(done)
        await self._broker.ack(message_id)
        await self._broker.clear_cancel(run_id)


def build_worker(settings: Settings) -> ResearchWorker:
    engine, sessions = create_session_factory(settings.mysql_dsn)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    broker = RedisResearchBroker(
        redis,
        stream=settings.redis_job_stream,
        group=settings.redis_consumer_group,
        consumer=settings.redis_consumer_name,
        cancel_ttl_seconds=settings.redis_cancel_ttl_seconds,
        claim_idle_ms=settings.redis_claim_idle_ms,
    )

    async def dispose_engine() -> None:
        await engine.dispose()

    return ResearchWorker(
        SqlAlchemyRunRepository(sessions),
        broker,
        settings,
        worker_id=settings.redis_consumer_name,
        close_callback=dispose_engine,
    )
