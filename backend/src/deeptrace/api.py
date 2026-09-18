"""DeepResearch HTTP API and dashboard."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis

from deeptrace.config import Settings
from deeptrace.domain import normalize_research_mode
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.repository import SqlAlchemyRunRepository
from deeptrace.queue.redis_streams import RedisResearchBroker
from deeptrace.runtime.distributed import DistributedResearchRuntime
from deeptrace.runtime.local import LocalResearchRuntime
from deeptrace.runtime.errors import ThreadBusyError
from deeptrace.runtime.models import RunMode, RunRecord
from deeptrace.runtime.protocol import ResearchRuntime


class ResearchRequest(BaseModel):
    """Create-research request accepted by all runtime modes.

    ``thread_id`` continues an existing conversation thread; omit it to start
    a new thread (a fresh identifier is assigned).
    """

    question: str = Field(min_length=1)
    mode: str = "workflow"
    thread_id: str | None = Field(default=None, max_length=128)

    @field_validator("mode")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        """Canonical values pass through; legacy aliases normalize at the boundary."""
        return normalize_research_mode(value).value


def _record_to_response(record: RunRecord) -> dict[str, Any]:
    data = record.model_dump(mode="json")
    data["events"] = record.events[-200:]
    return data


def _resolve_dashboard_dir() -> Path | None:
    """定位已构建的前端产物目录。

    Docker 镜像把 ``frontend/dist`` 拷贝到包内 static 目录；
    本地构建产物留在仓库根目录的 ``frontend/dist``。
    两处都没有时返回 None，根路由返回 503 引导构建。
    """
    packaged = Path(__file__).parent / "static"
    if (packaged / "index.html").is_file():
        return packaged
    local = Path(__file__).parents[3] / "frontend" / "dist"
    if (local / "index.html").is_file():
        return local
    return None


def _build_runtime(
    settings: Settings, runs_dir: Path | str | None
) -> tuple[ResearchRuntime, Callable[[], Awaitable[None]] | None]:
    if getattr(settings, "runtime_mode", "local") == "local":
        from deeptrace.application.assembly import build_harness_runtime

        bundle = build_harness_runtime(settings, runs_dir=runs_dir or "runs")
        return (
            LocalResearchRuntime(
                settings,
                runs_dir or "runs",
                application=bundle.service,
                context_factory=bundle.context_factory,
            ),
            bundle.aclose,
        )

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

    app = FastAPI(title="DeepResearch API", lifespan=lifespan)

    @app.post("/researches")
    async def create_research(request: ResearchRequest) -> dict[str, Any]:
        try:
            record = await selected_runtime.create(
                request.question.strip(),
                request.mode,
                thread_id=request.thread_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ThreadBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "id": record.id,
            "status": record.status,
            "thread_id": record.thread_id,
        }

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
                "thread_id": record.thread_id,
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

    dashboard_dir = _resolve_dashboard_dir()
    if dashboard_dir is not None:
        app.mount(
            "/assets",
            StaticFiles(directory=dashboard_dir / "assets"),
            name="assets",
        )

    @app.get("/", response_class=FileResponse)
    async def dashboard() -> FileResponse:
        if dashboard_dir is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "前端产物未构建：开发时使用 frontend/ 的 Vite dev server，"
                    "或先执行 npm run build / docker compose --build 构建镜像。"
                ),
            )
        return FileResponse(dashboard_dir / "index.html")

    return app


def main() -> None:
    """Start the local development API."""

    import uvicorn

    # 工厂模式：避免模块导入时读取环境变量或初始化外部依赖，
    # 测试可以在无 .env 的干净环境里安全 import create_app。
    uvicorn.run(create_app(), host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
