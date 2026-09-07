import asyncio
from decimal import Decimal

from fastapi.testclient import TestClient

import deeptrace
from deeptrace.api import create_app
from deeptrace.models import AgentResult, TokenUsage, UsageBreakdown
from deeptrace.runtime.local import LocalResearchRuntime


class FakeAgent:
    async def arun(self, question):
        return AgentResult(
            status="completed",
            answer="报告",
            sources=["https://example.com"],
            steps=1,
            events=[],
            termination_reason="completed",
            search_queries=[],
            provider_usage=TokenUsage(),
            role_usage=UsageBreakdown(),
            estimated_cost_usd=Decimal(0),
            stage_seconds={},
        )

    async def aclose(self):
        pass


def test_public_router_selects_multi_agent_and_rejects_unknown(monkeypatch):
    marker = FakeAgent()
    monkeypatch.setattr(deeptrace, "build_multi_agent", lambda settings, event: marker)
    assert deeptrace.build_real_agent(object(), mode="multi_agent") is marker
    try:
        deeptrace.build_real_agent(object(), mode="unknown")
    except ValueError as exc:
        assert "basic" in str(exc) and "multi_agent" in str(exc)
    else:
        raise AssertionError("unknown mode was silently routed to Basic")


def test_api_accepts_and_persists_multi_agent_mode(tmp_path):
    selected = []

    def factory(settings, on_event=None, mode="basic"):
        selected.append(mode)
        return FakeAgent()

    runtime = LocalResearchRuntime(object(), tmp_path, factory)
    app = create_app(settings=object(), runtime=runtime)
    with TestClient(app) as client:
        created = client.post(
            "/researches", json={"question": "研究问题", "mode": "multi_agent"}
        )
        run_id = created.json()["id"]
        for _ in range(50):
            response = client.get(f"/researches/{run_id}").json()
            if response["status"] == "completed":
                break
            asyncio.run(asyncio.sleep(0.001))
        assert response["mode"] == "multi_agent"
        assert selected == ["multi_agent"]


def test_api_rejects_unknown_mode(tmp_path):
    with TestClient(create_app(settings=object(), runs_dir=tmp_path)) as client:
        assert client.post(
            "/researches", json={"question": "问题", "mode": "unknown"}
        ).status_code == 422


def test_frontend_exposes_multi_agent_mode_and_coordination_events(tmp_path):
    with TestClient(create_app(settings=object(), runs_dir=tmp_path)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'value="multi_agent"' in page.text
        assert "planning.started" in page.text
        assert "replanning.started" in page.text
        assert "replanning.completed" in page.text
        assert "supervisor.dispatched" in page.text
        assert "supervisor.retry" in page.text
        assert "supervisor.fallback" in page.text
        assert "plan.finish_rejected" in page.text
        assert "researcher.queued" in page.text
        assert "researcher.started" in page.text
        assert "researcher.completed" in page.text
        assert "tool.batch_limited" in page.text
