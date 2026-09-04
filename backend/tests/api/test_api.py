import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from deeptrace.api import create_app
from deeptrace.models import RunEvent, TokenUsage, UsageBreakdown


class FakeAgent:
    def __init__(self, on_event):
        self._on_event = on_event

    async def arun(self, question):
        self._on_event(
            RunEvent(event_type="planning.completed", message="计划已生成")
        )
        return SimpleNamespace(
            status="completed",
            answer="# 报告\n\n正文[^1]。",
            sources=["https://example.com/a"],
            steps=3,
            events=[],
            token_metrics=[],
            termination_reason="completed",
            plan=None,
            sections=[],
            used_note_ids=["note-01"],
            provider_usage=TokenUsage(total_tokens=42),
            role_usage=UsageBreakdown(),
            estimated_cost_usd=None,
        )

    async def aclose(self):
        return None


def test_api_creates_and_completes_research(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    created = {}

    def fake_build(settings, on_event=None):
        created["on_event"] = on_event
        return FakeAgent(on_event)

    import deeptrace.api as api_module

    monkeypatch.setattr(api_module, "build_real_agent", fake_build)
    client = TestClient(create_app(runs_dir=tmp_path / "runs"))
    resp = client.post(
        "/researches", json={"question": "2024 年 AI Agent 热点新闻？"}
    )
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    for _ in range(100):
        data = client.get(f"/researches/{run_id}").json()
        if data["status"] == "completed":
            break
        asyncio.run(asyncio.sleep(0.05))

    assert data["status"] == "completed"
    assert data["answer"].startswith("# 报告")
    assert data["usage"]["total_tokens"] == 42
    assert any(
        event["event_type"] == "planning.completed"
        for event in data["events"]
    )
    # 结果已持久化
    persisted = (tmp_path / "runs" / f"{run_id}.json").read_text(
        encoding="utf-8"
    )
    assert "2024 年 AI Agent 热点新闻？" in persisted


def test_api_list_and_missing_run(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import deeptrace.api as api_module

    monkeypatch.setattr(
        api_module, "build_real_agent", lambda settings, on_event=None: FakeAgent(on_event)
    )
    client = TestClient(create_app(runs_dir=tmp_path / "runs"))
    assert client.get("/researches").json() == []
    assert client.get("/researches/missing").status_code == 404
