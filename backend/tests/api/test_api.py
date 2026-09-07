import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

from deeptrace.api import create_app
from deeptrace.models import RunEvent, TokenUsage, UsageBreakdown
from deeptrace.runtime.local import LocalResearchRuntime
from deeptrace.runtime.models import RunRecord


class FakeAgent:
    def __init__(self, on_event):
        self._on_event = on_event

    async def arun(self, question):
        self._on_event(RunEvent(event_type="planning.completed", message="查询已生成"))
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
            unresolved_gaps=[],
        )

    async def aclose(self):
        return None


class FakeRuntime:
    def __init__(self) -> None:
        self.created = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def create(self, question, mode):
        self.created.append((question, mode))
        return RunRecord(
            id="run-1",
            question=question,
            mode=mode,
            created_at=datetime.now(UTC),
        )

    async def list(self):
        return []

    async def get(self, run_id):
        return None

    async def cancel(self, run_id):
        return None


def test_api_creates_and_completes_basic_research(tmp_path) -> None:
    from fastapi.testclient import TestClient

    runtime = LocalResearchRuntime(
        SimpleNamespace(),
        tmp_path / "runs",
        lambda settings, on_event=None, mode="basic": FakeAgent(on_event),
    )
    client = TestClient(
        create_app(settings=SimpleNamespace(), runtime=runtime)
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
    assert any(event["event_type"] == "planning.completed" for event in data["events"])
    persisted = json.loads(
        (tmp_path / "runs" / f"{run_id}.json").read_text(encoding="utf-8")
    )
    assert persisted["search_queries"] == ["技术进展", question]
    assert persisted["termination_reason"] == "completed"


def test_api_delegates_creation_to_injected_runtime() -> None:
    from fastapi.testclient import TestClient

    runtime = FakeRuntime()
    with TestClient(create_app(settings=object(), runtime=runtime)) as client:
        response = client.post(
            "/researches", json={"question": "研究问题", "mode": "deep"}
        )

    assert response.status_code == 200
    assert response.json() == {"id": "run-1", "status": "pending"}
    assert runtime.created == [("研究问题", "deep")]
    assert runtime.started is True
    assert runtime.stopped is True


def test_api_list_and_missing_run(tmp_path) -> None:
    from fastapi.testclient import TestClient

    runtime = LocalResearchRuntime(
        SimpleNamespace(),
        tmp_path / "runs",
        lambda settings, on_event=None, mode="basic": FakeAgent(on_event),
    )
    client = TestClient(
        create_app(settings=SimpleNamespace(), runtime=runtime)
    )
    assert client.get("/researches").json() == []
    assert client.get("/researches/missing").status_code == 404


def test_api_routes_deep_mode_and_persists_selection(tmp_path):
    from fastapi.testclient import TestClient

    selected = []

    def factory(settings, on_event=None, mode="basic"):
        selected.append(mode)
        return FakeAgent(on_event)

    runtime = LocalResearchRuntime(SimpleNamespace(), tmp_path, factory)
    with TestClient(
        create_app(settings=SimpleNamespace(), runtime=runtime)
    ) as client:
        run_id = client.post(
            "/researches", json={"question": "研究问题", "mode": "deep"}
        ).json()["id"]
        for _ in range(100):
            data = client.get(f"/researches/{run_id}").json()
            if data["status"] == "completed":
                break
            asyncio.run(asyncio.sleep(0.01))
        assert data["mode"] == "deep"
        assert selected == ["deep"]
        assert (
            json.loads((tmp_path / f"{run_id}.json").read_text(encoding="utf-8"))[
                "mode"
            ]
            == "deep"
        )
        assert (
            client.post(
                "/researches", json={"question": "问题", "mode": "invalid"}
            ).status_code
            == 422
        )


def test_agent_construction_failure_is_terminal_and_persisted(tmp_path):
    from fastapi.testclient import TestClient

    def broken(*args, **kwargs):
        raise ValueError("Provider initialization failed: secret-test-key")

    runtime = LocalResearchRuntime(SimpleNamespace(), tmp_path, broken)
    with TestClient(
        create_app(settings=SimpleNamespace(), runtime=runtime)
    ) as client:
        run_id = client.post(
            "/researches", json={"question": "问题", "mode": "deep"}
        ).json()["id"]
        for _ in range(100):
            data = client.get(f"/researches/{run_id}").json()
            if data["status"] == "failed":
                break
            asyncio.run(asyncio.sleep(0.01))
        assert data["status"] == "failed"
        assert data["finished_at"]
        assert (tmp_path / f"{run_id}.json").exists()
        assert "secret-test-key" not in json.dumps(data)
        assert "secret-test-key" not in (tmp_path / f"{run_id}.json").read_text(encoding="utf-8")
