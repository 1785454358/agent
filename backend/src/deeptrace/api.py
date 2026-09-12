"""ResearchPilot HTTP API and dashboard."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis

from deeptrace.config import Settings
from deeptrace.domain import normalize_research_mode
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.repository import SqlAlchemyRunRepository
from deeptrace.queue.redis_streams import RedisResearchBroker
from deeptrace.runtime.distributed import DistributedResearchRuntime
from deeptrace.runtime.local import LocalResearchRuntime
from deeptrace.runtime.models import RunMode, RunRecord
from deeptrace.runtime.protocol import ResearchRuntime


class ResearchRequest(BaseModel):
    """Create-research request accepted by all runtime modes."""

    question: str = Field(min_length=1)
    mode: str = "workflow"

    @field_validator("mode")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        """Canonical values pass through; legacy aliases normalize at the boundary."""
        return normalize_research_mode(value).value


def _record_to_response(record: RunRecord) -> dict[str, Any]:
    data = record.model_dump(mode="json")
    data["events"] = record.events[-200:]
    return data


def _build_runtime(
    settings: Settings, runs_dir: Path | str | None
) -> tuple[ResearchRuntime, Callable[[], Awaitable[None]] | None]:
    if getattr(settings, "runtime_mode", "local") == "local":
        return LocalResearchRuntime(settings, runs_dir or "runs"), None

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
    return (
        DistributedResearchRuntime(SqlAlchemyRunRepository(sessions), broker),
        engine.dispose,
    )


def create_app(
    settings: Settings | None = None,
    *,
    runs_dir: Path | str | None = None,
    runtime: ResearchRuntime | None = None,
) -> FastAPI:
    """Build the API with an injectable lifecycle runtime."""

    app_settings = settings or Settings.from_env()
    if runtime is None:
        selected_runtime, dispose_resources = _build_runtime(app_settings, runs_dir)
    else:
        selected_runtime, dispose_resources = runtime, None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            await selected_runtime.start()
            yield
        finally:
            try:
                await selected_runtime.stop()
            finally:
                if dispose_resources is not None:
                    await dispose_resources()

    app = FastAPI(title="ResearchPilot API", lifespan=lifespan)

    @app.post("/researches")
    async def create_research(request: ResearchRequest) -> dict[str, Any]:
        try:
            record = await selected_runtime.create(request.question.strip(), request.mode)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": record.id, "status": record.status}

    @app.get("/researches")
    async def list_researches() -> list[dict[str, Any]]:
        records = await selected_runtime.list()
        return [
            {
                "id": record.id,
                "question": record.question,
                "mode": record.mode,
                "status": record.status,
                "created_at": record.created_at.isoformat(),
            }
            for record in records
        ]

    @app.get("/researches/{run_id}")
    async def get_research(run_id: str) -> dict[str, Any]:
        record = await selected_runtime.get(run_id)
        if record is None:
            raise HTTPException(404, "运行不存在")
        return _record_to_response(record)

    @app.post("/researches/{run_id}/cancel")
    async def cancel_research(run_id: str) -> dict[str, str]:
        record = await selected_runtime.cancel(run_id)
        if record is None:
            raise HTTPException(404, "运行不存在")
        return {"id": run_id, "status": record.status}

    @app.get("/researches/{run_id}/events")
    async def stream_events(
        run_id: str,
        last_event_id: int = Header(0, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        if await selected_runtime.get(run_id) is None:
            raise HTTPException(404, "运行不存在")

        async def generator():
            async for event in selected_runtime.events(run_id, last_event_id):
                if event.event_type == "done":
                    yield f"id: {event.id}\nevent: done\ndata: {{}}\n\n"
                    break
                data = json.dumps(event.payload, ensure_ascii=False)
                yield f"id: {event.id}\ndata: {data}\n\n"

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=FileResponse)
    async def dashboard() -> FileResponse:
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    return app


app = create_app()


def main() -> None:
    """Start the local development API."""

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
