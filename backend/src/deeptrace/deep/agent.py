"""Plan-and-Execute coordinator with feedback-triggered replanning."""

import asyncio
import time

from deeptrace.deep.executor import execute_task
from deeptrace.deep.planner import plan_research
from deeptrace.deep.runtime import RunRuntime
from deeptrace.models import AgentResult
from deeptrace.observability import estimate_usage_cost


class DeepResearchAgent:
    def __init__(self, *, model, writer, tools, settings, on_event=None):
        self.model = model
        self.writer = writer
        self.tools = tools
        self.settings = settings
        self.on_event = on_event

    async def arun(self, question: str) -> AgentResult:
        question = question.strip()
        if not question:
            raise ValueError("问题不能为空")
        runtime = RunRuntime(self.settings, self.on_event)
        self.tools.reset()
        self.tools.set_question(question)
        # 注入工具配额回调，组合工具内部按实际抓取页数计数。
        self.tools.quota = runtime.claim_tool
        history = []
        pending = []
        reason = "completed"
        max_tasks = getattr(self.settings, "deep_max_tasks", 6)
        max_steps = getattr(self.settings, "deep_max_steps", 12)
        replans = 0
        steps = 0
        try:
            plan = await plan_research(
                self.model,
                runtime,
                question=question,
                history=history,
                pending=[],
                slots=max_tasks,
                initial=True,
            )
            if plan is None:
                reason = "planning_failed"
            else:
                pending = list(plan.tasks)
            while pending:
                if not runtime.remaining_tools():
                    reason = "tool_call_limit"
                    break
                if len(history) >= max_tasks or steps >= max_steps:
                    reason = (
                        "task_budget" if len(history) >= max_tasks else "step_budget"
                    )
                    break
                completed = {
                    entry["task"]["id"]
                    for entry in history
                    if entry["status"] == "completed" and not entry["gaps"]
                }
                task = next(
                    (task for task in pending if set(task.depends_on) <= completed),
                    None,
                )
                if task is not None:
                    runtime.emit(
                        "task.started",
                        f"开始研究 {task.id}：{task.objective}",
                        task_id=task.id,
                        success_criteria=task.success_criteria,
                    )
                    feedback, used_steps = await execute_task(
                        self.model,
                        runtime,
                        self.tools,
                        task,
                        history,
                        max_steps - steps,
                    )
                    steps += used_steps
                    pending.remove(task)
                    history.append({"task": task.model_dump(), **feedback.model_dump()})
                    runtime.emit(
                        "task.completed",
                        f"{task.id} "
                        + {
                            "completed": "完成",
                            "partial": "部分完成",
                            "blocked": "受阻",
                        }.get(feedback.status, feedback.status)
                        + (
                            "；缺口：" + "；".join(feedback.gaps)
                            if feedback.gaps
                            else ""
                        ),
                        task_id=task.id,
                        status=feedback.status,
                    )
                    needs_review = (
                        feedback.status == "blocked" or not pending
                    )
                else:
                    needs_review = True
                if not runtime.remaining_tools():
                    reason = "tool_call_limit"
                    break
                if not needs_review:
                    continue
                if replans >= getattr(self.settings, "deep_max_replans", 2):
                    if task is None:
                        reason = "dependency_blocked"
                        break
                    continue
                if len(history) >= max_tasks or steps >= max_steps:
                    if (
                        pending
                        or history[-1]["status"] != "completed"
                        or history[-1]["gaps"]
                    ):
                        reason = (
                            "task_budget"
                            if len(history) >= max_tasks
                            else "step_budget"
                        )
                    break
                replans += 1
                revised = await plan_research(
                    self.model,
                    runtime,
                    question=question,
                    history=history,
                    pending=pending,
                    slots=max_tasks - len(history),
                    contexts=self.tools.contexts,
                )
                if revised is None:
                    reason = "replanning_failed"
                    break
                if revised.finish:
                    break
                # 保留未执行的待办任务，重规划只追加针对缺口的补充任务。
                # 不允许补充任务替换、删除或与原待办/已执行任务 ID 冲突。
                existing_ids = {task.id for task in pending} | {
                    entry["task"]["id"] for entry in history
                }
                supplement = [
                    task for task in revised.tasks if task.id not in existing_ids
                ]
                for entry in history:
                    if entry["status"] == "blocked" or entry["gaps"]:
                        entry["status"] = "superseded"
                pending = pending + supplement
        except Exception as exc:
            reason = "provider_failure"
            runtime.emit(
                "research.failed",
                "模型调用失败，使用已有研究资料生成报告",
                error=type(exc).__name__,
            )

        if reason in {"tool_call_limit", "task_budget", "step_budget"}:
            runtime.emit(
                "limit.reached",
                "研究达到次数上限，开始生成报告：" + reason,
                reason=reason,
            )
        unresolved = [task.objective for task in pending]
        for entry in history:
            if entry["status"] == "blocked" or (
                entry["gaps"] and entry["status"] != "superseded"
            ):
                unresolved.extend(entry["gaps"] or [entry["task"]["objective"]])
        if unresolved and reason == "completed":
            reason = "incomplete_research"
        if not self.tools.contexts and reason == "completed":
            reason = "no_sources"
        runtime.emit(
            "research.completed",
            f"深度研究结束：{len(history)} 个已执行任务，{len(self.tools.contexts)} 个已读来源",
            task_count=len(history),
            source_count=len(self.tools.contexts),
            termination_reason=reason,
        )
        if unresolved:
            runtime.emit("research.gaps", "尚未解决：" + "；".join(unresolved))
        result = await self._write(question, reason, unresolved, runtime)
        try:
            await self.tools.persist()
        except Exception as exc:
            runtime.emit(
                "memory.failed",
                "资料缓存写入失败，本次报告仍可使用",
                error=type(exc).__name__,
            )
        runtime.emit(
            "run.completed",
            f"研究任务完成；总耗时 {time.monotonic() - runtime.started:.1f} 秒；总消耗 Token {runtime.role_usage.total.total_tokens:,}",
            elapsed_seconds=round(time.monotonic() - runtime.started, 3),
            total_tokens=runtime.role_usage.total.total_tokens,
            input_tokens=runtime.role_usage.total.input_tokens,
            output_tokens=runtime.role_usage.total.output_tokens,
            tool_calls=runtime.tool_calls,
            execution_rounds=steps,
        )
        return AgentResult(
            status=result[0],
            answer=result[1],
            sources=list(self.tools.contexts),
            steps=runtime.steps,
            events=runtime.events,
            termination_reason=result[2],
            search_queries=list(self.tools.queries),
            provider_usage=runtime.role_usage.total,
            role_usage=runtime.role_usage,
            stage_seconds=runtime.stage_seconds,
            estimated_cost_usd=estimate_usage_cost(
                runtime.role_usage.total,
                getattr(self.settings, "input_cost_per_million", None),
                getattr(self.settings, "output_cost_per_million", None),
            ),
            unresolved_gaps=unresolved,
        )

    async def _write(self, question, reason, unresolved, runtime):
        contexts = list(self.tools.contexts.values())
        # Fair per-source allocation keeps later tasks from disappearing at the
        # Writer's 60k boundary. All input remains source text, not agent claims.
        share = max(1, 50000 // max(1, len(contexts)))
        context = "\n\n".join(text[:share] for text in contexts)
        writer_input = dict(
            question=question,
            context=context,
            sources=list(self.tools.contexts),
            language="zh-CN",
            termination_reason=reason
            + ("；未解决：" + "；".join(unresolved) if unresolved else ""),
        )
        started = time.monotonic()
        runtime.emit("writing.started", "正在汇总原始资料并生成报告")
        if context:
            runtime.steps += 1
        outcome = await self.writer.awrite(**writer_input)
        runtime.account("writer", outcome.usage)
        runtime.stage_seconds["writer"] = time.monotonic() - started
        if outcome.used_fallback:
            runtime.emit("writing.fallback", "Writer 未完成正式报告，展示可用资料")
            if reason == "completed":
                reason = "writing_failed"
        runtime.emit("writing.completed", "研究报告已生成")
        return (
            ("completed" if reason == "completed" else "partial"),
            outcome.markdown,
            reason,
        )

    def run(self, question):
        return asyncio.run(self.arun(question))

    async def aclose(self):
        await self.tools.aclose()
