"""LangGraph node service for Supervisor planning and Researcher execution."""

from __future__ import annotations

import asyncio
import copy

from deeptrace.multi_agent.models import (
    PlannedTask,
    ResearchAssignment,
    ResearcherResult,
)
from deeptrace.multi_agent.researcher import Researcher
from deeptrace.multi_agent.state import (
    compact_task_history,
    leaf_gaps,
    ready_task_ids,
    task_source_urls,
)
from deeptrace.multi_agent.supervisor import build_gap_followups
from deeptrace.multi_agent.tools import ResearcherTools


class MultiAgentWorkflowNodes:
    """Own process-local dependencies used by serializable graph nodes."""

    def __init__(
        self,
        *,
        model,
        writer,
        resources,
        settings,
        runtime,
        supervisor,
        researcher_factory=None,
    ) -> None:
        self.model = model
        self.writer = writer
        self.resources = resources
        self.settings = settings
        self.runtime = runtime
        self.supervisor = supervisor
        self.researcher_factory = researcher_factory or self._default_researcher

    def _default_researcher(
        self,
        runtime,
        question: str,
        current_date: str,
        timezone: str,
    ) -> Researcher:
        return Researcher(
            self.model,
            runtime,
            question=question,
            current_date=current_date,
            timezone=timezone,
        )

    def _telemetry(self) -> dict:
        return {
            "events": list(self.runtime.events),
            "role_usage": copy.deepcopy(self.runtime.role_usage),
            "stage_seconds": dict(self.runtime.stage_seconds),
            "step_count": self.runtime.steps,
        }

    @staticmethod
    def _add_assignments(state: dict, drafts) -> tuple[dict, list[str], int]:
        tasks = dict(state["tasks"])
        next_number = int(state["next_task_number"])
        task_ids: list[str] = []
        for draft in drafts:
            task_id = f"r{next_number}"
            next_number += 1
            assignment = ResearchAssignment(id=task_id, **draft.model_dump())
            tasks[task_id] = PlannedTask(assignment=assignment)
            task_ids.append(task_id)
        return tasks, task_ids, next_number

    async def plan_node(self, state: dict) -> dict:
        self.runtime.emit("planning.started", "主管正在制定持久研究计划")
        remaining = int(self.settings.multi_agent_max_researchers)
        max_assignments = min(
            remaining, int(self.settings.multi_agent_max_batch_size)
        )
        outcome = await self.supervisor.plan(
            state["question"],
            current_date=state["current_date"],
            timezone=state["timezone"],
            remaining_slots=remaining,
            max_assignments=max_assignments,
        )
        decision = outcome.decision
        tasks = dict(state["tasks"])
        next_number = int(state["next_task_number"])
        if decision.action == "dispatch":
            tasks, _, next_number = self._add_assignments(
                state, decision.assignments[:max_assignments]
            )
            ready = ready_task_ids(tasks)
            termination_reason = ""
            final_gaps: list[str] = []
            self.runtime.emit(
                "planning.completed",
                "研究计划已生成："
                + "；".join(
                    f"{task_id} {tasks[task_id].assignment.objective}"
                    for task_id in ready
                ),
                task_ids=",".join(ready),
            )
        else:
            ready = []
            termination_reason = "planning_failed"
            final_gaps = list(decision.gaps)
            self.runtime.emit(
                "planning.failed",
                "主管未能生成可执行研究计划",
                gaps="；".join(final_gaps),
            )
        return {
            "tasks": tasks,
            "ready_task_ids": ready,
            "next_task_number": next_number,
            "supervisor_iteration": int(state["supervisor_iteration"]) + 1,
            "supervisor_circuit_open": outcome.circuit_open,
            "termination_reason": termination_reason,
            "final_gaps": final_gaps,
            **self._telemetry(),
        }

    async def execute_node(self, state: dict) -> dict:
        selected_ids = [
            task_id
            for task_id in state["ready_task_ids"]
            if task_id in state["tasks"]
            and state["tasks"][task_id].status == "pending"
        ]
        if not selected_ids:
            return {
                "ready_task_ids": [],
                "termination_reason": "no_ready_tasks",
                **self._telemetry(),
            }
        tasks = dict(state["tasks"])
        assignments = [tasks[task_id].assignment for task_id in selected_ids]
        if state["first_batch"]:
            leases = await self.resources.quota.allocate_initial(selected_ids)
        else:
            leases = await self.resources.quota.allocate_follow_up(selected_ids)
        self.runtime.emit(
            "supervisor.dispatched",
            "主管派发研究任务："
            + "；".join(
                f"{assignment.id} {assignment.objective}"
                for assignment in assignments
            ),
            task_ids=",".join(selected_ids),
        )
        previous_sources = sorted(
            {
                url
                for task in tasks.values()
                if task.result is not None
                for url in task.result.source_urls
            }
        )
        semaphore = asyncio.Semaphore(int(self.settings.multi_agent_concurrency))

        async def run_one(assignment: ResearchAssignment) -> ResearcherResult:
            lease = leases[assignment.id]
            self.runtime.emit(
                "researcher.queued",
                f"{assignment.id} 已进入研究队列：{assignment.objective}",
                task_id=assignment.id,
                local_tool_limit=lease.limit,
                parent_ids=",".join(assignment.parent_ids),
            )
            try:
                async with semaphore:
                    self.runtime.emit(
                        "researcher.started",
                        f"{assignment.id} 开始研究：{assignment.objective}",
                        task_id=assignment.id,
                        local_tool_limit=lease.limit,
                        parent_ids=",".join(assignment.parent_ids),
                    )
                    if lease.limit < 2:
                        self.runtime.emit(
                            "quota.reached",
                            f"{assignment.id} 未执行：可分配网络额度不足",
                            task_id=assignment.id,
                            local_tool_limit=lease.limit,
                        )
                        return ResearcherResult(
                            task_id=assignment.id,
                            status="blocked",
                            summary="剩余工具额度不足以完成一次搜索和一次原文读取。",
                            source_urls=[],
                            gaps=[
                                f"{item}：未研究"
                                for item in assignment.required_outputs
                            ],
                            stop_reason="global_tool_limit",
                        )
                    tools = None
                    try:
                        tools = ResearcherTools(
                            assignment,
                            self.resources,
                            lease,
                            user_question=state["question"],
                        )
                        researcher = self.researcher_factory(
                            self.runtime,
                            state["question"],
                            state["current_date"],
                            state["timezone"],
                        )
                        return await researcher.run(assignment, tools)
                    except asyncio.CancelledError:
                        raise
                    except Exception:  # noqa: BLE001 - isolate one Researcher
                        return ResearcherResult(
                            task_id=assignment.id,
                            status="blocked",
                            summary="研究员执行失败，其他独立任务继续运行。",
                            source_urls=(
                                sorted(tools.read_sources)
                                if tools is not None
                                else []
                            ),
                            gaps=[
                                f"{item}：研究员执行失败"
                                for item in assignment.required_outputs
                            ],
                            stop_reason="provider_failure",
                        )
            finally:
                await lease.release()

        batch_results = await asyncio.gather(
            *(run_one(assignment) for assignment in assignments)
        )
        for assignment, result in zip(assignments, batch_results, strict=True):
            tasks[assignment.id] = PlannedTask(
                assignment=assignment,
                status=result.status,
                result=result,
            )
            self.runtime.emit(
                "researcher.completed",
                f"{assignment.id} "
                + {
                    "completed": "完成",
                    "partial": "部分完成",
                    "blocked": "受阻",
                }[result.status]
                + ("；缺口：" + "；".join(result.gaps) if result.gaps else ""),
                task_id=assignment.id,
                status=result.status,
                stop_reason=result.stop_reason,
                source_count=len(result.source_urls),
            )
        return {
            "tasks": tasks,
            "ready_task_ids": [],
            "first_batch": False,
            "sources_before_batch": previous_sources,
            **self._telemetry(),
        }

    async def replan_node(self, state: dict) -> dict:
        """Review one completed batch and either dispatch gaps or terminate."""
        tasks = dict(state["tasks"])
        gaps = leaf_gaps(tasks)
        has_followup = any(task.assignment.parent_ids for task in tasks.values())
        current_sources = task_source_urls(tasks)
        previous_sources = set(state.get("sources_before_batch", []))

        if has_followup and gaps and not (current_sources - previous_sources):
            self.runtime.emit(
                "replanning.completed",
                "补查未增加新来源，停止重复研究",
                termination_reason="stagnant",
            )
            return {
                "tasks": tasks,
                "ready_task_ids": [],
                "final_sufficient": False,
                "final_gaps": gaps,
                "termination_reason": "stagnant",
                **self._telemetry(),
            }

        max_researchers = int(self.settings.multi_agent_max_researchers)
        remaining_slots = max(0, max_researchers - len(tasks))
        max_iterations = int(
            state.get(
                "max_supervisor_iterations",
                self.settings.multi_agent_max_supervisor_rounds,
            )
        )
        current_iteration = int(state["supervisor_iteration"])
        decision_has_followup_round = current_iteration + 1 < max_iterations
        quota_capacity = self.resources.quota.remaining // 2
        max_assignments = min(
            remaining_slots,
            int(self.settings.multi_agent_max_batch_size),
            quota_capacity,
        )
        can_dispatch = bool(
            gaps and max_assignments > 0 and decision_has_followup_round
        )

        self.runtime.emit(
            "replanning.started",
            "主管正在评估研究结果并补充未解决任务",
        )
        outcome = await self.supervisor.replan(
            state["question"],
            compact_task_history(tasks),
            current_date=state["current_date"],
            timezone=state["timezone"],
            remaining_slots=remaining_slots,
            max_assignments=max_assignments if can_dispatch else 0,
            circuit_open=bool(state["supervisor_circuit_open"]),
        )
        decision = outcome.decision
        next_iteration = current_iteration + 1
        drafts = []
        if decision.action == "dispatch" and can_dispatch:
            drafts = decision.assignments[:max_assignments]
        elif (
            decision.action == "finish"
            and not decision.sufficient
            and can_dispatch
        ):
            self.runtime.emit(
                "plan.finish_rejected",
                "主管尝试在存在缺口和执行容量时结束，已改为定向补查",
                reason_code="incomplete_with_capacity",
            )
            drafts = build_gap_followups(
                compact_task_history(tasks),
                max_assignments=max_assignments,
            )

        if drafts:
            tasks, new_ids, next_number = self._add_assignments(state, drafts)
            self.runtime.emit(
                "replanning.completed",
                "主管补充研究计划："
                + "；".join(
                    f"{task_id} {tasks[task_id].assignment.objective}"
                    for task_id in new_ids
                ),
                task_ids=",".join(new_ids),
            )
            return {
                "tasks": tasks,
                "ready_task_ids": new_ids,
                "next_task_number": next_number,
                "supervisor_iteration": next_iteration,
                "supervisor_circuit_open": outcome.circuit_open,
                "termination_reason": "",
                "final_gaps": [],
                **self._telemetry(),
            }

        if decision.action == "finish" and decision.sufficient and not gaps:
            reason = "completed"
            final_sufficient = True
            final_gaps: list[str] = []
        else:
            final_sufficient = False
            final_gaps = gaps or list(decision.gaps)
            if remaining_slots <= 0:
                reason = "researcher_limit"
            elif self.resources.quota.remaining < 2:
                reason = "global_tool_limit"
            elif not decision_has_followup_round:
                reason = "supervisor_round_limit"
            else:
                reason = "incomplete_research"
        self.runtime.emit(
            "replanning.completed",
            "主管结束研究"
            + ("，检查项已满足" if final_sufficient else "并保留未解决问题"),
            termination_reason=reason,
            sufficient=final_sufficient,
        )
        return {
            "tasks": tasks,
            "ready_task_ids": [],
            "supervisor_iteration": next_iteration,
            "supervisor_circuit_open": outcome.circuit_open,
            "final_sufficient": final_sufficient,
            "final_gaps": final_gaps,
            "termination_reason": reason,
            **self._telemetry(),
        }
