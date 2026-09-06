import asyncio
from types import SimpleNamespace

from deeptrace.models import UsageBreakdown
from deeptrace.multi_agent.models import (
    AssignmentDraft,
    PlannedTask,
    ResearchAssignment,
    ResearcherResult,
    SupervisorDecision,
    SupervisorOutcome,
)
from deeptrace.multi_agent.nodes import MultiAgentWorkflowNodes
from deeptrace.multi_agent.runtime import MultiAgentRuntime, QuotaManager


def settings(**overrides):
    values = {
        "multi_agent_max_researchers": 6,
        "multi_agent_max_batch_size": 3,
        "multi_agent_concurrency": 2,
        "multi_agent_max_supervisor_rounds": 3,
        "multi_agent_call_timeout_seconds": 1,
        "input_cost_per_million": None,
        "output_cost_per_million": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def initial_state(*, tasks=None, ready=None):
    return {
        "question": "2025 AI 热点",
        "current_date": "2026-09-06",
        "timezone": "Asia/Shanghai",
        "tasks": tasks or {},
        "ready_task_ids": ready or [],
        "next_task_number": 1,
        "supervisor_iteration": 0,
        "supervisor_circuit_open": False,
        "first_batch": True,
        "final_sufficient": False,
        "final_gaps": [],
        "termination_reason": "",
        "research_context": "",
        "final_sources": [],
        "final_answer": "",
        "events": [],
        "role_usage": UsageBreakdown(),
        "stage_seconds": {},
        "step_count": 0,
        "max_supervisor_iterations": 3,
        "sources_before_batch": [],
    }


def draft(name):
    return AssignmentDraft(
        objective=f"研究{name}",
        required_outputs=[f"{name}结果"],
        excluded_scope=[],
        source_guidance=["官方来源"],
    )


def assignment(task_id):
    return ResearchAssignment(id=task_id, **draft(task_id).model_dump())


class Resources:
    def __init__(self):
        self.quota = QuotaManager(total=30, per_researcher=10)


class Writer:
    async def awrite(self, **kwargs):
        raise AssertionError("execute tests must not call Writer")


class PlanningSupervisor:
    async def plan(self, *args, **kwargs):
        return SupervisorOutcome(
            decision=SupervisorDecision(
                action="dispatch",
                rationale="三个独立方向",
                assignments=[draft("技术"), draft("产业")],
            )
        )


def test_plan_node_adds_stable_pending_tasks():
    async def scenario():
        current_settings = settings()
        runtime = MultiAgentRuntime(current_settings)
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=runtime,
            supervisor=PlanningSupervisor(),
        )
        update = await nodes.plan_node(initial_state())
        assert list(update["tasks"]) == ["r1", "r2"]
        assert all(task.status == "pending" for task in update["tasks"].values())
        assert update["ready_task_ids"] == ["r1", "r2"]
        assert update["next_task_number"] == 3
        assert update["supervisor_iteration"] == 1

    asyncio.run(scenario())


def test_execute_node_runs_ready_tasks_with_bounded_concurrency():
    async def scenario():
        current_settings = settings(multi_agent_concurrency=2)
        runtime = MultiAgentRuntime(current_settings)
        resources = Resources()
        active = 0
        max_active = 0
        first_wave_ready = asyncio.Event()
        release_first_wave = asyncio.Event()

        class GatedResearcher:
            async def run(self, current_assignment, tools):
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                if active == 2:
                    first_wave_ready.set()
                if current_assignment.id in {"r1", "r2"}:
                    await release_first_wave.wait()
                active -= 1
                return ResearcherResult(
                    task_id=current_assignment.id,
                    status="completed",
                    summary="完成",
                    source_urls=[f"https://example.com/{current_assignment.id}"],
                    gaps=[],
                    stop_reason="completed",
                )

        tasks = {
            task_id: PlannedTask(assignment=assignment(task_id))
            for task_id in ("r1", "r2", "r3")
        }
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=resources,
            settings=current_settings,
            runtime=runtime,
            supervisor=PlanningSupervisor(),
            researcher_factory=lambda *args: GatedResearcher(),
        )
        run = asyncio.create_task(
            nodes.execute_node(initial_state(tasks=tasks, ready=list(tasks)))
        )
        await asyncio.wait_for(first_wave_ready.wait(), timeout=1)
        assert max_active == 2
        assert len(
            [event for event in runtime.events if event.event_type == "researcher.started"]
        ) == 2
        release_first_wave.set()
        update = await run
        assert all(task.status == "completed" for task in update["tasks"].values())
        assert update["ready_task_ids"] == []
        assert not update["first_batch"]
        assert len(
            [event for event in runtime.events if event.event_type == "researcher.queued"]
        ) == 3
        assert len(
            [event for event in runtime.events if event.event_type == "researcher.completed"]
        ) == 3
        assert all(lease._released for lease in resources.quota._leases.values())

    asyncio.run(scenario())


def test_execute_node_isolates_one_researcher_failure():
    async def scenario():
        current_settings = settings(multi_agent_concurrency=3)
        runtime = MultiAgentRuntime(current_settings)

        class SometimesFailingResearcher:
            async def run(self, current_assignment, tools):
                if current_assignment.id == "r1":
                    raise RuntimeError("private Provider failure")
                return ResearcherResult(
                    task_id=current_assignment.id,
                    status="completed",
                    summary="完成",
                    source_urls=[f"https://example.com/{current_assignment.id}"],
                    gaps=[],
                    stop_reason="completed",
                )

        tasks = {
            task_id: PlannedTask(assignment=assignment(task_id))
            for task_id in ("r1", "r2", "r3")
        }
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=runtime,
            supervisor=PlanningSupervisor(),
            researcher_factory=lambda *args: SometimesFailingResearcher(),
        )
        update = await nodes.execute_node(
            initial_state(tasks=tasks, ready=list(tasks))
        )
        assert update["tasks"]["r1"].status == "blocked"
        assert update["tasks"]["r2"].status == "completed"
        assert update["tasks"]["r3"].status == "completed"
        assert all("private" not in event.message for event in runtime.events)

    asyncio.run(scenario())
