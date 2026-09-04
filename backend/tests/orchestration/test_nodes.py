import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from deeptrace.agent.writer import WriterOutcome
from deeptrace.models import TokenUsage
from deeptrace.orchestration.budget import GlobalBudget
from deeptrace.orchestration.nodes import ResearchWorkflowNodes
from deeptrace.orchestration.research import QueryResearchResult


class _Planner:
    initial_results = None

    def __init__(self):
        self.calls = 0

    async def aplan(self, question, initial_results):
        self.calls += 1
        self.initial_results = initial_results
        return ["技术进展", question], TokenUsage(total_tokens=7), False, ""


class _Collector:
    initial_payload = {
        "ok": True,
        "results": [{"title": "背景", "url": "https://example.com"}],
    }

    def __init__(self):
        self.initial_search_calls = []

    async def asearch_initial(self, question):
        self.initial_search_calls.append(question)
        return self.initial_payload

    async def acollect(self, question, queries, initial_search):
        results = [
            QueryResearchResult(
                query=query,
                context=f"Content: {query}",
                sources=[f"https://example.com/{index}"],
                documents=[],
                candidate_count=1,
                fetch_success_count=1,
                fetch_failure_count=0,
                errors=[],
            )
            for index, query in enumerate(queries)
        ]
        return "Content: merged", {}, ["https://example.com/0"], results


class _Writer:
    def __init__(self):
        self.calls = 0

    async def awrite(self, **kwargs):
        self.calls += 1
        return WriterOutcome(
            markdown="# 报告",
            sources=list(kwargs["sources"]),
            usage=TokenUsage(total_tokens=11),
        )

    def fallback(self, **kwargs):
        return WriterOutcome(
            markdown="# 截止时间降级报告",
            sources=list(kwargs["sources"]),
            used_fallback=True,
        )


class _ExpiredBudget:
    reason = "time_budget"

    def stop_reason(self, _now):
        return self.reason

    async def record_usage(self, **_kwargs):
        return None


class _HangingPlanner:
    async def aplan(self, *_args):
        await asyncio.sleep(60)


class _HangingWriter(_Writer):
    async def awrite(self, **_kwargs):
        self.calls += 1
        await asyncio.sleep(60)


def _nodes():
    collector = _Collector()
    planner = _Planner()
    settings = SimpleNamespace(
        input_cost_per_million=None,
        output_cost_per_million=None,
    )
    return (
        ResearchWorkflowNodes(
            planner=planner,
            collector=collector,
            writer=_Writer(),
            settings=settings,
        ),
        collector,
        planner,
    )


def _state(question="问题"):
    return {
        "user_query": question,
        "search_queries": [],
        "initial_search": None,
        "documents": {},
        "research_context": "",
        "final_sources": [],
        "termination_reason": "",
        "started_at": (datetime.now(UTC) - timedelta(seconds=2)).isoformat(),
        "provider_usage": TokenUsage(
            input_tokens=3,
            output_tokens=4,
            total_tokens=7,
        ),
    }


def test_plan_node_searches_before_calling_planner() -> None:
    nodes, collector, planner = _nodes()

    update = asyncio.run(nodes.plan_node(_state()))

    assert collector.initial_search_calls == ["问题"]
    assert planner.initial_results == collector.initial_payload["results"]
    assert planner.calls == 1
    assert update["search_queries"] == ["技术进展", "问题"]
    assert [event.event_type for event in update["events"]] == [
        "planning.started",
        "planning.completed",
    ]


def test_plan_node_uses_original_question_when_deadline_expires_after_search() -> None:
    nodes, _collector, planner = _nodes()
    nodes.budget = _ExpiredBudget()

    update = asyncio.run(nodes.plan_node(_state()))

    assert planner.calls == 0
    assert update["search_queries"] == ["问题"]
    assert update["events"][-1].event_type == "planning.fallback"


def test_plan_node_is_bounded_by_global_remaining_time() -> None:
    nodes, _collector, _planner = _nodes()
    budget_settings = SimpleNamespace(
        max_runtime_seconds=0.02,
        max_fetched_pages=20,
        max_cost_usd=None,
    )
    nodes.planner = _HangingPlanner()
    nodes.budget = GlobalBudget(budget_settings, datetime.now(UTC))

    update = asyncio.run(
        asyncio.wait_for(nodes.plan_node(_state()), timeout=0.2)
    )

    assert update["search_queries"] == ["问题"]
    assert update["events"][-1].event_type == "planning.fallback"


def test_parallel_research_node_emits_query_events() -> None:
    nodes, _collector, _planner = _nodes()

    update = asyncio.run(
        nodes.parallel_research_node(
            {**_state(), "search_queries": ["a", "b"]}
        )
    )

    assert update["research_context"] == "Content: merged"
    event_types = [event.event_type for event in update["events"]]
    assert event_types.count("query.started") == 2
    assert event_types.count("query.completed") == 2
    assert event_types[-1] == "research.completed"
    assert all(not event_type.startswith("task.") for event_type in event_types)
    completed = [
        event for event in update["events"] if event.event_type == "query.completed"
    ]
    assert [event.details["query"] for event in completed] == ["a", "b"]


def test_writer_node_finishes_run_and_accounts_usage() -> None:
    nodes, _collector, _planner = _nodes()

    update = asyncio.run(
        nodes.writer_node(
            {
                **_state(),
                "research_context": "Content: merged",
                "final_sources": ["https://example.com/0"],
            }
        )
    )

    assert update["final_answer"] == "# 报告"
    assert update["termination_reason"] == "completed"
    assert update["role_usage"].writer.total_tokens == 11
    assert [event.event_type for event in update["events"]] == [
        "writing.completed",
        "run.completed",
    ]
    completed = update["events"][-1]
    assert completed.event_type == "run.completed"
    assert "总耗时" in completed.message
    assert "总消耗 Token 18" in completed.message
    assert completed.details["total_tokens"] == 18
    assert completed.details["input_tokens"] == 3
    assert completed.details["output_tokens"] == 4
    assert 2 <= completed.details["elapsed_seconds"] < 5


def test_writer_node_does_not_start_provider_after_global_deadline() -> None:
    nodes, _collector, _planner = _nodes()
    nodes.budget = _ExpiredBudget()
    writer = nodes.writer

    update = asyncio.run(
        nodes.writer_node(
            {
                **_state(),
                "research_context": "Content: merged",
                "final_sources": ["https://example.com/0"],
            }
        )
    )

    assert writer.calls == 0
    assert update["termination_reason"] == "time_budget"
    assert update["final_answer"] == "# 截止时间降级报告"


def test_writer_node_is_bounded_by_global_remaining_time() -> None:
    nodes, _collector, _planner = _nodes()
    budget_settings = SimpleNamespace(
        max_runtime_seconds=0.02,
        max_fetched_pages=20,
        max_cost_usd=None,
    )
    nodes.writer = _HangingWriter()
    nodes.budget = GlobalBudget(budget_settings, datetime.now(UTC))

    update = asyncio.run(
        asyncio.wait_for(
            nodes.writer_node(
                {
                    **_state(),
                    "research_context": "Content: merged",
                    "final_sources": ["https://example.com/0"],
                }
            ),
            timeout=0.2,
        )
    )

    assert update["termination_reason"] == "time_budget"
    assert update["final_answer"] == "# 截止时间降级报告"
