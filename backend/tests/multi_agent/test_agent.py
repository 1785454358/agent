import asyncio
from types import SimpleNamespace

from deeptrace.models import TokenUsage, UsageBreakdown
from deeptrace.multi_agent.agent import SupervisorResearchAgent
from deeptrace.multi_agent.models import (
    AssignmentDraft,
    ResearcherResult,
    SupervisorDecision,
    SupervisorOutcome,
)
from deeptrace.multi_agent.runtime import QuotaManager
from deeptrace.writer import WriterOutcome


class Supervisor:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.histories = []

    async def plan(self, question, **kwargs):
        self.histories.append([])
        return SupervisorOutcome(decision=self.decisions.pop(0))

    async def replan(self, question, history, **kwargs):
        self.histories.append(list(history))
        return SupervisorOutcome(decision=self.decisions.pop(0))


class Resources:
    def __init__(self):
        self.quota = QuotaManager(total=30, per_researcher=10)
        self.queries = []
        self.documents = {}
        self.memory = None
        self.closed = 0
        self.writer_max_chars = None

    def writer_material(self, results, max_chars=50_000):
        self.writer_max_chars = max_chars
        sources = [url for result in results for url in result.source_urls]
        return "\n".join(f"Source: {url}\n原文" for url in sources), sources

    async def aclose(self):
        self.closed += 1

    async def persist(self):
        pass


class Writer:
    async def awrite(self, **kwargs):
        return WriterOutcome(
            markdown="1 报告\n\n内容 [1]",
            sources=list(kwargs["sources"]),
            usage=TokenUsage(total_tokens=7),
        )


def draft(name):
    return AssignmentDraft(
        objective=name,
        required_outputs=[f"{name}结果"],
        excluded_scope=[],
        source_guidance=["官方来源"],
    )


def settings(**overrides):
    values = {
        "multi_agent_max_researchers": 6,
        "multi_agent_max_batch_size": 3,
        "multi_agent_concurrency": 2,
        "multi_agent_max_supervisor_rounds": 3,
        "multi_agent_max_researcher_rounds": 3,
        "multi_agent_call_timeout_seconds": 1,
        "input_cost_per_million": None,
        "output_cost_per_million": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_agent_adapts_compiled_graph_state_to_public_result():
    async def scenario():
        class Graph:
            def __init__(self):
                self.initial = None
                self.config = None

            async def ainvoke(self, initial, config):
                self.initial = initial
                self.config = config
                return {
                    **initial,
                    "final_answer": "1 报告",
                    "final_sources": ["https://example.com/a"],
                    "termination_reason": "completed",
                    "research_context": "原文",
                    "role_usage": UsageBreakdown(
                        writer=TokenUsage(total_tokens=7)
                    ),
                    "step_count": 2,
                }

        graph = Graph()
        agent = SupervisorResearchAgent(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=settings(),
            graph=graph,
        )
        result = await agent.arun(" 2025 AI 热点 ")
        assert graph.initial["question"] == "2025 AI 热点"
        assert graph.initial["current_date"]
        assert graph.initial["timezone"]
        assert graph.config["configurable"]["service"] is not None
        assert result.status == "completed"
        assert result.answer == "1 报告"
        assert result.sources == ["https://example.com/a"]
        assert result.provider_usage.total_tokens == 7

    asyncio.run(scenario())


def test_batch_runs_all_assignments_when_first_researcher_exhausts_lease():
    async def scenario():
        decisions = [
            SupervisorDecision(
                action="dispatch",
                rationale="并行覆盖",
                assignments=[draft("技术"), draft("产业"), draft("政策")],
            ),
            SupervisorDecision(
                action="finish",
                rationale="主要方向已覆盖",
                sufficient=True,
            ),
        ]
        supervisor = Supervisor(decisions)
        active = 0
        max_active = 0
        started = []

        class FakeResearcher:
            async def run(self, assignment, tools):
                nonlocal active, max_active
                started.append(assignment.id)
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0)
                if assignment.id == "r1":
                    while await tools.lease.acquire_network():
                        pass
                    status, gaps, reason = "partial", ["技术结果：未确认"], "local_tool_limit"
                else:
                    status, gaps, reason = "completed", [], "completed"
                active -= 1
                return ResearcherResult(
                    task_id=assignment.id,
                    status=status,
                    summary=f"{assignment.objective}交付",
                    source_urls=[f"https://example.com/{assignment.id}"],
                    gaps=gaps,
                    stop_reason=reason,
                )

        resources = Resources()
        agent = SupervisorResearchAgent(
            model=object(),
            writer=Writer(),
            resources=resources,
            settings=settings(),
            supervisor=supervisor,
            researcher_factory=lambda *args: FakeResearcher(),
        )
        result = await agent.arun("2025 AI 热点")
        assert started == ["r1", "r2", "r3"]
        assert max_active == 2
        assert len(supervisor.histories[1]) == 3
        assert result.status == "partial"
        assert len(result.sources) == 3
        assert "writer" in result.stage_seconds
        assert result.stage_seconds["writer"] >= 0
        assert resources.writer_max_chars == 30_000

    asyncio.run(scenario())


def test_researcher_started_means_the_task_acquired_a_worker_slot():
    async def scenario():
        supervisor = Supervisor(
            [
                SupervisorDecision(
                    action="dispatch",
                    rationale="并行覆盖",
                    assignments=[draft("技术"), draft("产业"), draft("政策")],
                ),
                SupervisorDecision(
                    action="finish",
                    rationale="方向已覆盖",
                    sufficient=True,
                ),
            ]
        )
        all_queued = asyncio.Event()
        first_running = asyncio.Event()
        release_first = asyncio.Event()
        emitted = []

        def on_event(event):
            emitted.append(event)
            queued = [item for item in emitted if item.event_type == "researcher.queued"]
            if len(queued) == 3:
                all_queued.set()

        class GatedResearcher:
            async def run(self, assignment, tools):
                if assignment.id == "r1":
                    await all_queued.wait()
                    first_running.set()
                    await release_first.wait()
                return ResearcherResult(
                    task_id=assignment.id,
                    status="completed",
                    summary="完成",
                    source_urls=[f"https://example.com/{assignment.id}"],
                    gaps=[],
                    stop_reason="completed",
                )

        current_settings = settings()
        current_settings.multi_agent_concurrency = 1
        agent = SupervisorResearchAgent(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            on_event=on_event,
            supervisor=supervisor,
            researcher_factory=lambda *args: GatedResearcher(),
        )
        run = asyncio.create_task(agent.arun("问题"))
        await asyncio.wait_for(first_running.wait(), timeout=0.5)
        assert len(
            [event for event in emitted if event.event_type == "researcher.queued"]
        ) == 3
        assert [
            event.details["task_id"]
            for event in emitted
            if event.event_type == "researcher.started"
        ] == ["r1"]
        release_first.set()
        await run

    asyncio.run(scenario())


def test_one_researcher_failure_isolated_and_report_is_partial():
    async def scenario():
        supervisor = Supervisor(
            [
                SupervisorDecision(
                    action="dispatch",
                    rationale="覆盖",
                    assignments=[draft("技术"), draft("政策")],
                ),
                SupervisorDecision(
                    action="finish",
                    rationale="存在关键缺口",
                    sufficient=False,
                    gaps=["技术方向未完成"],
                ),
            ]
        )

        class FakeResearcher:
            async def run(self, assignment, tools):
                if assignment.id == "r1":
                    raise RuntimeError("provider secret must not leak")
                return ResearcherResult(
                    task_id=assignment.id,
                    status="completed",
                    summary="政策完成",
                    source_urls=["https://example.com/r2"],
                    gaps=[],
                    stop_reason="completed",
                )

        agent = SupervisorResearchAgent(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=settings(multi_agent_max_researchers=2),
            supervisor=supervisor,
            researcher_factory=lambda *args: FakeResearcher(),
        )
        result = await agent.arun("问题")
        assert result.status == "partial"
        assert result.termination_reason == "researcher_limit"
        assert all("secret" not in event.message for event in result.events)
        assert len(supervisor.histories[1]) == 2

    asyncio.run(scenario())


def test_underfunded_assignments_are_visible_and_release_their_leases():
    async def scenario():
        supervisor = Supervisor(
            [
                SupervisorDecision(
                    action="dispatch",
                    rationale="尝试三个方向",
                    assignments=[draft("技术"), draft("产业"), draft("政策")],
                ),
                SupervisorDecision(
                    action="finish",
                    rationale="额度不足，保留缺口",
                    sufficient=False,
                    gaps=["产业和政策未研究"],
                ),
            ]
        )

        class FakeResearcher:
            async def run(self, assignment, tools):
                return ResearcherResult(
                    task_id=assignment.id,
                    status="completed",
                    summary="完成",
                    source_urls=[f"https://example.com/{assignment.id}"],
                    gaps=[],
                    stop_reason="completed",
                )

        resources = Resources()
        resources.quota = QuotaManager(total=5, per_researcher=5)
        agent = SupervisorResearchAgent(
            model=object(),
            writer=Writer(),
            resources=resources,
            settings=settings(multi_agent_max_researchers=3),
            supervisor=supervisor,
            researcher_factory=lambda *args: FakeResearcher(),
        )
        result = await agent.arun("问题")
        started = [
            event for event in result.events if event.event_type == "researcher.started"
        ]
        completed = [
            event
            for event in result.events
            if event.event_type == "researcher.completed"
        ]
        assert len(started) == 3
        assert len(completed) == 3
        assert all(lease._released for lease in resources.quota._leases.values())
        assert any(event.details["status"] == "blocked" for event in completed)

    asyncio.run(scenario())
