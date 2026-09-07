from datetime import UTC, datetime
from types import SimpleNamespace

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

import deeptrace.api as api_module
from deeptrace.api import _build_runtime, create_app
from deeptrace.runtime.distributed import DistributedResearchRuntime
from deeptrace.runtime.models import RunRecord, StoredEvent


class FakeDistributedRuntime:
    def __init__(self) -> None:
        self.created = []
        self.after_event_id = None
        self.run = RunRecord(
            id="run-1",
            question="研究问题",
            mode="multi_agent",
            created_at=datetime.now(UTC),
        )

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def create(self, question, mode):
        self.created.append((question, mode))
        return self.run.model_copy(update={"question": question, "mode": mode})

    async def list(self):
        return [self.run]

    async def get(self, run_id):
        return self.run if run_id == self.run.id else None

    async def cancel(self, run_id):
        if run_id != self.run.id:
            return None
        return self.run.model_copy(update={"status": "cancel_requested"})

    async def events(self, run_id, after_event_id=0):
        self.after_event_id = after_event_id
        for event in (
            StoredEvent(
                id=8,
                run_id=run_id,
                event_type="planning.completed",
                payload={
                    "event_type": "planning.completed",
                    "message": "规划完成",
                    "details": {"tasks": 3},
                    "ts": "2026-09-07T12:00:00+00:00",
                },
                created_at=datetime.now(UTC),
            ),
            StoredEvent(
                id=9,
                run_id=run_id,
                event_type="done",
                payload={"event_type": "done", "message": ""},
                created_at=datetime.now(UTC),
            ),
        ):
            yield event


def test_api_delegates_distributed_creation_without_running_agent() -> None:
    runtime = FakeDistributedRuntime()
    with TestClient(create_app(settings=object(), runtime=runtime)) as client:
        response = client.post(
            "/researches",
            json={"question": "  研究问题  ", "mode": "multi_agent"},
        )

    assert response.json() == {"id": "run-1", "status": "pending"}
    assert runtime.created == [("研究问题", "multi_agent")]


def test_sse_replays_after_last_event_id_and_emits_event_ids() -> None:
    runtime = FakeDistributedRuntime()
    with TestClient(create_app(settings=object(), runtime=runtime)) as client:
        with client.stream(
            "GET",
            "/researches/run-1/events",
            headers={"Last-Event-ID": "7"},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert runtime.after_event_id == 7
    assert "id: 8\n" in body
    assert '"event_type": "planning.completed"' in body
    assert "id: 9\nevent: done\ndata: {}\n\n" in body


def test_distributed_cancel_missing_run_and_health_routes() -> None:
    runtime = FakeDistributedRuntime()
    with TestClient(create_app(settings=object(), runtime=runtime)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/researches/missing").status_code == 404
        assert client.get("/researches/missing/events").status_code == 404
        assert client.post("/researches/missing/cancel").status_code == 404
        assert client.post("/researches/run-1/cancel").json() == {
            "id": "run-1",
            "status": "cancel_requested",
        }


@pytest.mark.asyncio
async def test_runtime_factory_selects_distributed_adapter(monkeypatch) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        api_module.Redis,
        "from_url",
        lambda *args, **kwargs: fake_redis,
    )
    settings = SimpleNamespace(
        runtime_mode="distributed",
        mysql_dsn="sqlite+aiosqlite:///:memory:",
        redis_url="redis://unused/0",
        redis_job_stream="jobs",
        redis_consumer_group="workers",
        redis_consumer_name="api",
        redis_cancel_ttl_seconds=60,
        redis_claim_idle_ms=1_000,
    )

    runtime, cleanup = _build_runtime(settings, None)

    assert isinstance(runtime, DistributedResearchRuntime)
    assert cleanup is not None
    await runtime.stop()
    await cleanup()
