import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from deeptrace.api import create_app
from deeptrace.domain import ResponseMode
from deeptrace.runtime.local import LocalResearchRuntime
from deeptrace.runtime.models import RunRecord


class FakeAgent:
    def __init__(self, on_event):
        self._on_event = on_event

    async def arun(self, question):
        self._on_event({"event_type": "planning.completed", "message": "查询已生成"})
        return SimpleNamespace(
            status="completed",
            answer="# 报告\n\n正文。",
            sources=["https://example.com/a"],
            steps=3,
            events=[],
            termination_reason="completed",
            search_queries=["技术进展", question],
            provider_usage=SimpleNamespace(total_tokens=42),
            role_usage=SimpleNamespace(),
            estimated_cost_usd=None,
            stage_seconds={"plan": 0.1, "parallel_research": 0.2, "writer": 0.1},
            unresolved_gaps=[],
        )

    async def aclose(self):
        return None


class FakeRuntime:
    def __init__(self) -> None:
        self.created: list[Any] = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def create(self, question, mode, thread_id=None):
        self.created.append((question, mode, thread_id))
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


class FakeOutcome:
    response_mode = ResponseMode.ANSWER
    content = "简洁回答 [1]"
    partial_reason = None
    cited_evidence_ids = ["evidence-1"]


class FakeEvidence:
    canonical_url = "https://example.com/a"


class FakeEvidenceStore:
    async def get_many(self, tenant_id, ids):
        return [FakeEvidence() for _ in ids]


class FakeContext:
    workspace_id = "workspace-1"
    evidence_store = FakeEvidenceStore()


class FakeApplication:
    async def invoke(self, request, *, config, context):
        return FakeOutcome()


def build_local_runtime(tmp_path):
    return LocalResearchRuntime(
        SimpleNamespace(),
        tmp_path / "runs",
        application=FakeApplication(),
        context_factory=lambda run_id, on_event=None: FakeContext(),
    )


def wait_for_completed(client, run_id):
    data: dict[str, Any] = {}
    for _ in range(200):
        data = client.get(f"/researches/{run_id}").json()
        if data["status"] in {"completed", "partial", "failed"}:
            return data
        asyncio.run(asyncio.sleep(0.01))
    return data


def test_api_creates_and_completes_research(tmp_path) -> None:
    from fastapi.testclient import TestClient

    runtime = build_local_runtime(tmp_path)
    client = TestClient(create_app(settings=SimpleNamespace(), runtime=runtime))
    question = "2024 年 AI Agent 热点新闻？"
    response = client.post(
        "/researches", json={"question": question, "thread_id": "thread-9"}
    )
    assert response.status_code == 200
    body = response.json()
    run_id = body["id"]
    assert body["thread_id"] == "thread-9"

    data = wait_for_completed(client, run_id)

    assert data["status"] == "completed"
    assert data["answer"] == "简洁回答 [1]"
    assert data["sources"] == ["https://example.com/a"]
    assert data["thread_id"] == "thread-9"
    assert any(
        event["event_type"] == "response.completed" for event in data["events"]
    )
    persisted = json.loads(
        (tmp_path / "runs" / f"{run_id}.json").read_text(encoding="utf-8")
    )
    assert persisted["termination_reason"] == "completed"


def test_api_delegates_creation_to_injected_runtime() -> None:
    from fastapi.testclient import TestClient

    runtime = FakeRuntime()
    with TestClient(create_app(settings=object(), runtime=runtime)) as client:
        response = client.post(
            "/researches", json={"question": "研究问题", "mode": "deep"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": "run-1",
        "status": "pending",
        "thread_id": "",
    }
    assert runtime.created == [("研究问题", "plan_execute", None)]
    assert runtime.started is True
    assert runtime.stopped is True


def test_api_list_and_missing_run(tmp_path) -> None:
    from fastapi.testclient import TestClient

    runtime = build_local_runtime(tmp_path)
    client = TestClient(create_app(settings=SimpleNamespace(), runtime=runtime))
    assert client.get("/researches").json() == []
    assert client.get("/researches/missing").status_code == 404


def test_api_routes_plan_execute_mode_and_persists_selection(tmp_path):
    from fastapi.testclient import TestClient

    runtime = build_local_runtime(tmp_path)
    with TestClient(
        create_app(settings=SimpleNamespace(), runtime=runtime)
    ) as client:
        run_id = client.post(
            "/researches", json={"question": "研究问题", "mode": "deep"}
        ).json()["id"]
        data = wait_for_completed(client, run_id)
        assert data["mode"] == "plan_execute"
        assert (
            json.loads(
                (tmp_path / "runs" / f"{run_id}.json").read_text(encoding="utf-8")
            )[
                "mode"
            ]
            == "plan_execute"
        )
        assert (
            client.post(
                "/researches", json={"question": "问题", "mode": "invalid"}
            ).status_code
            == 422
        )


def test_legacy_basic_record_reads_back_as_workflow(tmp_path) -> None:
    from fastapi.testclient import TestClient

    runtime = build_local_runtime(tmp_path)
    client = TestClient(create_app(settings=SimpleNamespace(), runtime=runtime))

    created = client.post(
        "/researches", json={"question": "旧问题", "mode": "basic"}
    ).json()["id"]
    data = client.get(f"/researches/{created}").json()

    assert data["mode"] == "workflow"
