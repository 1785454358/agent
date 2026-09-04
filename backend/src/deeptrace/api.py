"""DeepTrace API 服务：任务管理、SSE 事件流、运行持久化与 Web 仪表盘。

阶段 5 的产品化入口。每个研究请求创建独立运行记录（稳定 ID、状态、预算、
终止原因），后台任务执行完整研究管线，事件经 SSE 实时推送，结果与全部
事件持久化为 runs/<id>.json。/ 页面提供最小可用的研究仪表盘。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from deeptrace.agent.service import AgentResult, build_real_agent
from deeptrace.config import Settings
from deeptrace.models import RunEvent


class ResearchRequest(BaseModel):
    """创建研究任务的请求体。"""

    question: str = Field(min_length=1)


class RunRecord(BaseModel):
    """一次研究运行的可持久化记录。"""

    id: str
    question: str
    status: str = "pending"
    created_at: str
    finished_at: str | None = None
    answer: str = ""
    sources: list[str] = Field(default_factory=list)
    plan: dict[str, Any] | None = None
    sections: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    error: str | None = None


class _RunState:
    """注册表内的运行时状态：记录 + SSE 队列 + 后台任务。"""

    def __init__(self, record: RunRecord) -> None:
        self.record = record
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None

    def append_event(self, event: RunEvent) -> None:
        item = {
            **event.model_dump(),
            "ts": datetime.now(UTC).isoformat(),
        }
        self.record.events.append(item)
        self.queue.put_nowait(item)


def _record_to_response(record: RunRecord) -> dict[str, Any]:
    data = record.model_dump(mode="json")
    data["events"] = [
        {**item, "ts": item.get("ts")} for item in record.events[-200:]
    ]
    return data


def create_app(
    settings: Settings | None = None,
    *,
    runs_dir: Path | str | None = None,
) -> FastAPI:
    """构建 FastAPI 应用；settings/runs_dir 可注入以便测试。"""
    app_settings = settings or Settings.from_env()
    runs_path = Path(runs_dir) if runs_dir else Path("runs")
    runs_path.mkdir(parents=True, exist_ok=True)
    registry: dict[str, _RunState] = {}
    app = FastAPI(title="DeepTrace API")

    def _persist(record: RunRecord) -> None:
        path = runs_path / f"{record.id}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def _apply_result(record: RunRecord, result: AgentResult) -> None:
        record.status = result.status
        record.finished_at = datetime.now(UTC).isoformat()
        record.answer = result.answer
        record.sources = result.sources
        record.plan = (
            result.plan.model_dump(mode="json") if result.plan else None
        )
        record.sections = [
            section.model_dump(mode="json") for section in result.sections
        ]
        record.usage = {
            "total_tokens": result.provider_usage.total_tokens,
            "input_tokens": result.provider_usage.input_tokens,
            "output_tokens": result.provider_usage.output_tokens,
            "role_usage": result.role_usage.model_dump(mode="json"),
            "steps": result.steps,
        }

    async def _execute(record: RunRecord, state: _RunState) -> None:
        record.status = "running"
        agent = build_real_agent(
            app_settings, on_event=state.append_event
        )
        try:
            result = await agent.arun(record.question)
            _apply_result(record, result)
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.finished_at = datetime.now(UTC).isoformat()
            record.error = "运行被用户取消"
            raise
        except Exception as exc:
            record.status = "failed"
            record.finished_at = datetime.now(UTC).isoformat()
            record.error = f"{type(exc).__name__}: {exc}"
        finally:
            await agent.aclose()
            _persist(record)
            state.queue.put_nowait(None)

    @app.post("/researches")
    async def create_research(request: ResearchRequest) -> dict[str, Any]:
        record = RunRecord(
            id=uuid.uuid4().hex[:12],
            question=request.question.strip(),
            created_at=datetime.now(UTC).isoformat(),
        )
        if not record.question:
            raise HTTPException(400, "问题不能为空")
        state = _RunState(record)
        registry[record.id] = state
        state.task = asyncio.create_task(_execute(record, state))
        _persist(record)
        return {"id": record.id, "status": record.status}

    @app.get("/researches")
    async def list_researches() -> list[dict[str, Any]]:
        return [
            {
                "id": item.record.id,
                "question": item.record.question,
                "status": item.record.status,
                "created_at": item.record.created_at,
            }
            for item in registry.values()
        ]

    @app.get("/researches/{run_id}")
    async def get_research(run_id: str) -> dict[str, Any]:
        state = registry.get(run_id)
        if state is None:
            raise HTTPException(404, "运行不存在")
        return _record_to_response(state.record)

    @app.post("/researches/{run_id}/cancel")
    async def cancel_research(run_id: str) -> dict[str, str]:
        state = registry.get(run_id)
        if state is None:
            raise HTTPException(404, "运行不存在")
        if state.task is not None and not state.task.done():
            state.task.cancel()
        return {"id": run_id, "status": "cancelling"}

    @app.get("/researches/{run_id}/events")
    async def stream_events(run_id: str) -> StreamingResponse:
        state = registry.get(run_id)
        if state is None:
            raise HTTPException(404, "运行不存在")

        async def generator():
            while True:
                item = await state.queue.get()
                if item is None:
                    yield "event: done\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            generator(), media_type="text/event-stream"
        )

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        return HTMLResponse(_DASHBOARD_HTML)

    return app


_DASHBOARD_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>DeepTrace 研究仪表盘</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 24px; background: #f6f7f9; }
  h1 { font-size: 20px; }
  .card { background: #fff; border: 1px solid #e3e5e8; border-radius: 8px;
          padding: 16px; margin-bottom: 16px; }
  input { width: 60%; padding: 8px; }
  button { padding: 8px 16px; }
  pre { white-space: pre-wrap; word-break: break-word; background: #fafafa;
        padding: 12px; border-radius: 6px; max-height: 480px; overflow: auto; }
  .event { font-size: 12px; color: #555; }
</style>
</head>
<body>
<h1>DeepTrace 研究仪表盘</h1>
<div class="card">
  <input id="q" placeholder="输入研究问题，例如：2024 年 AI Agent 领域有哪些热点新闻？">
  <button onclick="start()">开始研究</button>
  <span id="status"></span>
</div>
<div class="card"><b>研究事件</b><div id="events" class="event"></div></div>
<div class="card"><b>最终报告</b><pre id="report">（等待运行）</pre></div>
<script>
let runId = null;
async function start() {
  const question = document.getElementById('q').value.trim();
  const resp = await fetch('/researches', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question})
  });
  runId = (await resp.json()).id;
  document.getElementById('status').textContent = '运行中：' + runId;
  listen();
  poll();
}
function listen() {
  const es = new EventSource('/researches/' + runId + '/events');
  es.onmessage = (e) => {
    const item = JSON.parse(e.data);
    const div = document.getElementById('events');
    div.innerHTML += `<div>[${
      (item.ts || '').slice(11, 19)
    }] ${item.event_type}: ${item.message}</div>`;
  };
  es.addEventListener('done', () => es.close());
}
async function poll() {
  const resp = await fetch('/researches/' + runId);
  const data = await resp.json();
  if (['completed', 'partial', 'failed', 'cancelled'].includes(data.status)) {
    document.getElementById('status').textContent =
      '状态：' + data.status + '；报告来源 ' + data.sources.length + ' 个';
    document.getElementById('report').textContent = data.answer || data.error;
    return;
  }
  setTimeout(poll, 2000);
}
</script>
</body>
</html>
"""

app = create_app()


def main() -> None:
    """`python -m deeptrace.api` 启动服务的入口。"""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
