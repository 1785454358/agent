import asyncio
import json
from types import SimpleNamespace

from deeptrace.api import create_app
from deeptrace.models import RunEvent, TokenUsage, UsageBreakdown


class FakeAgent:
    def __init__(self, on_event):
        self._on_event = on_event

    async def arun(self, question):
        self._on_event(
            RunEvent(event_type="planning.completed", message="查询已生成")
        )
        return SimpleNamespace(
            status="completed",
            answer="# 报告\n\n正文。",
            sources=["https://example.com/a"],
            steps=3,
            events=[],
            termination_reason="completed",
            search_queries=["技术进展", question],
            provider_usage=TokenUsage(total_tokens=42),
            role_usage=UsageBreakdown(),
            estimated_cost_usd=None,
            stage_seconds={"plan": 0.1, "parallel_research": 0.2, "writer": 0.1},
        )

    async def aclose(self):
        return None


def test_api_creates_and_completes_basic_research(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import deeptrace.api as api_module

    monkeypatch.setattr(
        api_module,
        "build_real_agent",
        lambda settings, on_event=None: FakeAgent(on_event),
    )
    client = TestClient(
        create_app(settings=SimpleNamespace(), runs_dir=tmp_path / "runs")
    )
    question = "2024 年 AI Agent 热点新闻？"
    response = client.post("/researches", json={"question": question})
    assert response.status_code == 200
    run_id = response.json()["id"]

    for _ in range(100):
        data = client.get(f"/researches/{run_id}").json()
        if data["status"] == "completed":
            break
        asyncio.run(asyncio.sleep(0.01))

    assert data["status"] == "completed"
    assert data["search_queries"] == ["技术进展", question]
    assert "plan" not in data
    assert "sections" not in data
    assert data["usage"]["total_tokens"] == 42
    assert data["usage"]["stage_seconds"]["parallel_research"] == 0.2
    assert any(
        event["event_type"] == "planning.completed" for event in data["events"]
    )
    persisted = json.loads(
        (tmp_path / "runs" / f"{run_id}.json").read_text(encoding="utf-8")
    )
    assert persisted["search_queries"] == ["技术进展", question]
    assert persisted["termination_reason"] == "completed"


def test_api_list_and_missing_run(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import deeptrace.api as api_module

    monkeypatch.setattr(
        api_module,
        "build_real_agent",
        lambda settings, on_event=None: FakeAgent(on_event),
    )
    client = TestClient(
        create_app(settings=SimpleNamespace(), runs_dir=tmp_path / "runs")
    )
    assert client.get("/researches").json() == []
    assert client.get("/researches/missing").status_code == 404
