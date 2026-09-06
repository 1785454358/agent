import asyncio
import json
from types import SimpleNamespace

from deeptrace.models import TokenUsage, UsageBreakdown
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
from deeptrace.multi_agent.state import route_after_plan, route_after_replan
from deeptrace.writer import WriterOutcome


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
        self.persisted = 0

    def writer_material(self, results, max_chars=50_000):
        sources = [url for result in results for url in result.source_urls]
        context = "\n\n".join(f"Source: {url}\n原文" for url in sources)
        return context[:max_chars], sources

    async def persist(self):
        self.persisted += 1


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


class ReplanningSupervisor:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    async def replan(self, *args, **kwargs):
        self.calls += 1
        return self.outcome


def terminal_task(
    task_id,
    status="partial",
    gaps=None,
    *,
    parents=(),
    required_outputs=None,
    url=None,
):
    current_assignment = ResearchAssignment(
        id=task_id,
        objective=f"研究 {task_id}",
        required_outputs=list(required_outputs or [f"{task_id}结果"]),
        excluded_scope=[],
        source_guidance=["官方来源"],
        parent_ids=list(parents),
    )
    current_gaps = list(
        gaps or ([] if status == "completed" else [f"{task_id}缺口"])
    )
    current_result = ResearcherResult(
        task_id=task_id,
        status=status,
        summary=f"{task_id}交付",
        source_urls=[url or f"https://example.com/{task_id}"],
        gaps=current_gaps,
        stop_reason="completed" if status == "completed" else "round_limit",
    )
    return PlannedTask(
        assignment=current_assignment,
        status=status,
        result=current_result,
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
        started = next(
            event
            for event in runtime.events
            if event.event_type == "researcher.started"
        )
        assert json.loads(started.details["required_outputs"]) == ["r1结果"]
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


def test_replan_rejects_insufficient_finish_while_capacity_remains():
    async def scenario():
        tasks = {
            "r1": terminal_task("r1", gaps=["产品发布未确认"]),
            "r2": terminal_task("r2", gaps=["监管政策未确认"]),
            "r3": terminal_task("r3", gaps=["科研突破未确认"]),
        }
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="finish",
                    rationale="2025 has not occurred yet",
                    sufficient=False,
                    gaps=["2025 has not occurred yet"],
                )
            )
        )
        current_settings = settings()
        runtime = MultiAgentRuntime(current_settings)
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=runtime,
            supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["next_task_number"] = 4
        state["supervisor_iteration"] = 1
        state["first_batch"] = False
        update = await nodes.replan_node(state)
        assert supervisor.calls == 1
        assert update["termination_reason"] == ""
        assert update["ready_task_ids"] == ["r4", "r5", "r6"]
        assert all(
            update["tasks"][task_id].status == "pending"
            for task_id in update["ready_task_ids"]
        )
        assert [
            update["tasks"][task_id].assignment.parent_ids
            for task_id in update["ready_task_ids"]
        ] == [["r1"], ["r2"], ["r3"]]
        assert any(
            event.event_type == "plan.finish_rejected"
            for event in runtime.events
        )

    asyncio.run(scenario())


def test_replan_compiles_broad_supervisor_draft_into_exact_gap_tasks():
    async def scenario():
        tasks = {
            "r1": terminal_task(
                "r1",
                gaps=["巴黎峰会成果未确认", "欧盟法案实施未确认"],
            )
        }
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="dispatch",
                    rationale="补查政策方向",
                    assignments=[
                        AssignmentDraft(
                            objective="整理全球 AI 监管与政策热点",
                            required_outputs=["完成政策整理"],
                            parent_ids=["r1"],
                        )
                    ],
                )
            )
        )
        current_settings = settings()
        runtime = MultiAgentRuntime(current_settings)
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=runtime,
            supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["next_task_number"] = 2
        state["supervisor_iteration"] = 1
        state["first_batch"] = False

        update = await nodes.replan_node(state)

        assert update["ready_task_ids"] == ["r2", "r3"]
        assignments = [
            update["tasks"][task_id].assignment
            for task_id in update["ready_task_ids"]
        ]
        assert [item.required_outputs for item in assignments] == [
            ["巴黎峰会成果未确认"],
            ["欧盟法案实施未确认"],
        ]
        assert [item.objective for item in assignments] == [
            "补充并核实：巴黎峰会成果未确认",
            "补充并核实：欧盟法案实施未确认",
        ]
        assert all(item.parent_ids == ["r1"] for item in assignments)
        completed = next(
            event
            for event in runtime.events
            if event.event_type == "replanning.completed"
        )
        assert "巴黎峰会成果未确认" in completed.message
        assert "欧盟法案实施未确认" in completed.message

    asyncio.run(scenario())


def test_replan_rejects_sufficient_finish_when_leaf_gap_remains():
    async def scenario():
        tasks = {"r1": terminal_task("r1", gaps=["官方发布日期未确认"])}
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="finish",
                    rationale="误判为已经完成",
                    sufficient=True,
                )
            )
        )
        current_settings = settings()
        runtime = MultiAgentRuntime(current_settings)
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=runtime,
            supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["next_task_number"] = 2
        state["supervisor_iteration"] = 1
        state["first_batch"] = False
        update = await nodes.replan_node(state)
        assert update["ready_task_ids"] == ["r2"]
        assert update["tasks"]["r2"].assignment.parent_ids == ["r1"]
        assert any(
            event.event_type == "plan.finish_rejected"
            for event in runtime.events
        )

    asyncio.run(scenario())


def test_replan_finishes_when_completed_tasks_have_no_open_gaps():
    async def scenario():
        tasks = {"r1": terminal_task("r1", status="completed")}
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="finish",
                    rationale="检查项已完成",
                    sufficient=True,
                )
            )
        )
        current_settings = settings()
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=MultiAgentRuntime(current_settings),
            supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["supervisor_iteration"] = 1
        state["first_batch"] = False
        update = await nodes.replan_node(state)
        assert supervisor.calls == 0
        assert update["termination_reason"] == "completed"
        assert update["final_sufficient"]
        assert update["final_gaps"] == []
        assert route_after_replan({**state, **update}) == "writer"

    asyncio.run(scenario())


def test_replan_cannot_add_tasks_after_researcher_limit():
    async def scenario():
        tasks = {
            f"r{index}": terminal_task(f"r{index}", gaps=[f"缺口 {index}"])
            for index in range(1, 7)
        }
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="finish",
                    rationale="仍有缺口",
                    sufficient=False,
                    gaps=["仍有缺口"],
                )
            )
        )
        current_settings = settings()
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=MultiAgentRuntime(current_settings),
            supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["next_task_number"] = 7
        state["supervisor_iteration"] = 1
        state["first_batch"] = False
        update = await nodes.replan_node(state)
        assert supervisor.calls == 0
        assert update["ready_task_ids"] == []
        assert update["termination_reason"] == "researcher_limit"
        assert len(update["tasks"]) == 6

    asyncio.run(scenario())


def test_replan_skips_supervisor_when_global_tool_limit_is_terminal():
    async def scenario():
        tasks = {"r1": terminal_task("r1", gaps=["政策日期未确认"])}
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="finish",
                    rationale="不应调用",
                    sufficient=False,
                    gaps=["不应使用"],
                )
            )
        )
        resources = Resources()
        resources.quota.consumed = 29
        current_settings = settings()
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=resources,
            settings=current_settings,
            runtime=MultiAgentRuntime(current_settings),
            supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["next_task_number"] = 2
        state["supervisor_iteration"] = 1
        state["first_batch"] = False
        update = await nodes.replan_node(state)
        assert supervisor.calls == 0
        assert update["termination_reason"] == "global_tool_limit"
        assert update["final_gaps"] == ["政策日期未确认"]

    asyncio.run(scenario())


def test_replan_skips_supervisor_when_no_followup_round_remains():
    async def scenario():
        tasks = {
            "r1": terminal_task("r1", status="completed"),
            "r5": terminal_task(
                "r5",
                gaps=["联合国全球AI治理对话机制成立月份未明确"],
                parents=("r3",),
            ),
        }
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="finish",
                    rationale="不应调用",
                    sufficient=False,
                    gaps=["不应使用"],
                )
            )
        )
        current_settings = settings()
        runtime = MultiAgentRuntime(current_settings)
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=runtime,
            supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["next_task_number"] = 6
        state["supervisor_iteration"] = 2
        state["first_batch"] = False
        update = await nodes.replan_node(state)
        assert supervisor.calls == 0
        assert update["termination_reason"] == "supervisor_round_limit"
        assert update["final_gaps"] == [
            "联合国全球AI治理对话机制成立月份未明确"
        ]
        assert not any(
            event.event_type in {"supervisor.retry", "supervisor.fallback"}
            for event in runtime.events
        )

    asyncio.run(scenario())


def test_replan_stops_after_followup_adds_no_new_source():
    async def scenario():
        tasks = {
            "r1": terminal_task("r1", gaps=["旧缺口"], url="https://example.com/a"),
            "r2": terminal_task(
                "r2",
                gaps=["补查后仍未确认"],
                parents=("r1",),
                required_outputs=["旧缺口"],
                url="https://example.com/a",
            ),
        }
        supervisor = ReplanningSupervisor(
            SupervisorOutcome(
                decision=SupervisorDecision(
                    action="dispatch",
                    rationale="再次补查",
                    assignments=[draft("再次补查")],
                )
            )
        )
        current_settings = settings()
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=Writer(),
            resources=Resources(),
            settings=current_settings,
            runtime=MultiAgentRuntime(current_settings),
            supervisor=supervisor,
        )
        state = initial_state(tasks=tasks)
        state["next_task_number"] = 3
        state["supervisor_iteration"] = 2
        state["first_batch"] = False
        state["sources_before_batch"] = ["https://example.com/a"]
        update = await nodes.replan_node(state)
        assert update["ready_task_ids"] == []
        assert update["termination_reason"] == "stagnant"
        assert update["final_gaps"] == ["补查后仍未确认"]
        assert supervisor.calls == 0

    asyncio.run(scenario())


def test_graph_routes_only_when_ready_tasks_exist():
    state = initial_state()
    assert route_after_plan(state) == "writer"
    state["ready_task_ids"] = ["r1"]
    assert route_after_plan(state) == "execute"
    assert route_after_replan(state) == "execute"
    state["termination_reason"] = "researcher_limit"
    assert route_after_replan(state) == "writer"


def test_writer_node_uses_all_terminal_results_and_authoritative_date():
    async def scenario():
        class CapturingWriter:
            def __init__(self):
                self.kwargs = None

            async def awrite(self, **kwargs):
                self.kwargs = kwargs
                return WriterOutcome(
                    markdown="1 报告\n\n内容 [1]",
                    sources=list(kwargs["sources"]),
                    usage=TokenUsage(total_tokens=7),
                )

        writer = CapturingWriter()
        resources = Resources()
        current_settings = settings()
        runtime = MultiAgentRuntime(current_settings)
        nodes = MultiAgentWorkflowNodes(
            model=object(),
            writer=writer,
            resources=resources,
            settings=current_settings,
            runtime=runtime,
            supervisor=PlanningSupervisor(),
        )
        state = initial_state(
            tasks={
                "r1": terminal_task("r1", status="completed"),
                "r2": terminal_task("r2", status="completed"),
            }
        )
        state["termination_reason"] = "completed"
        state["final_sufficient"] = True
        update = await nodes.writer_node(state)
        assert writer.kwargs["current_date"] == "2026-09-06"
        assert writer.kwargs["timezone"] == "Asia/Shanghai"
        assert writer.kwargs["sources"] == [
            "https://example.com/r1",
            "https://example.com/r2",
        ]
        assert update["final_answer"].startswith("1 报告")
        assert update["final_sources"] == writer.kwargs["sources"]
        assert update["termination_reason"] == "completed"
        assert update["role_usage"].writer.total_tokens == 7
        assert resources.persisted == 1
        assert runtime.events[-1].event_type == "run.completed"

    asyncio.run(scenario())
