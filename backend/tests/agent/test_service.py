import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from deeptrace.agent.service import ResearchAgent, _initial_research_state
from deeptrace.models import RunEvent, TokenUsage, UsageBreakdown


class _Graph:
    async def ainvoke(self, initial, config):
        assert initial["user_query"] == "研究问题"
        assert config["configurable"]["service"] is not None
        return {
            **initial,
            "search_queries": ["技术进展", "研究问题"],
            "final_answer": "# 报告",
            "final_sources": ["https://example.com/a"],
            "events": [RunEvent(event_type="run.completed", message="完成")],
            "step_count": 3,
            "provider_usage": TokenUsage(
                input_tokens=100, output_tokens=20, total_tokens=120
            ),
            "role_usage": UsageBreakdown(
                planner=TokenUsage(total_tokens=30),
                writer=TokenUsage(total_tokens=90),
            ),
            "stage_seconds": {"plan": 1.0, "parallel_research": 2.0},
            "termination_reason": "completed",
        }


class _Fetcher:
    closed = False

    async def aclose(self):
        self.closed = True


def _settings():
    return SimpleNamespace(
        use_memory=False,
        input_cost_per_million=Decimal("2"),
        output_cost_per_million=Decimal("6"),
    )


def test_initial_research_state_is_fully_initialized() -> None:
    state = _initial_research_state(
        "研究问题", started_at=datetime(2026, 9, 4, tzinfo=UTC)
    )

    assert state["user_query"] == "研究问题"
    assert state["search_queries"] == []
    assert state["initial_search"] is None
    assert state["research_context"] == ""
    assert state["documents"] == {}
    assert state["final_sources"] == []
    for key in {"notes", "chunks", "research_plan", "used_note_ids"}:
        assert key not in state


def test_agent_maps_basic_graph_result() -> None:
    fetcher = _Fetcher()
    agent = ResearchAgent(
        graph=_Graph(),
        nodes=SimpleNamespace(budget=None),
        collector=SimpleNamespace(cache_documents=lambda _documents: None),
        fetcher=fetcher,
        settings=_settings(),
    )

    result = asyncio.run(agent.arun("  研究问题  "))

    assert result.status == "completed"
    assert result.answer == "# 报告"
    assert result.sources == ["https://example.com/a"]
    assert result.search_queries == ["技术进展", "研究问题"]
    assert result.provider_usage.total_tokens == 120
    assert result.estimated_cost_usd == Decimal("0.00032")
    assert result.stage_seconds["parallel_research"] == 2.0
    assert not hasattr(result, "plan")
    assert not hasattr(result, "sections")
    assert not hasattr(result, "token_metrics")


def test_agent_rejects_empty_question_and_closes_fetcher() -> None:
    fetcher = _Fetcher()
    agent = ResearchAgent(
        graph=_Graph(),
        nodes=SimpleNamespace(budget=None),
        collector=SimpleNamespace(cache_documents=lambda _documents: None),
        fetcher=fetcher,
        settings=_settings(),
    )

    with pytest.raises(ValueError, match="问题不能为空"):
        asyncio.run(agent.arun("   "))
    asyncio.run(agent.aclose())
    assert fetcher.closed is True
