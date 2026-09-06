"""Independent bounded ReAct Researcher."""

from __future__ import annotations

import asyncio
import json
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from deeptrace.multi_agent.models import (
    FINISH_TOOL,
    RESEARCHER_MODEL_TOOLS,
    ResearcherResult,
)
from deeptrace.multi_agent.prompts import researcher_messages


class Researcher:
    def __init__(
        self,
        model,
        runtime,
        *,
        question: str = "",
        current_date: str = "",
        timezone: str = "",
    ) -> None:
        self.model = model
        self.runtime = runtime
        self.question = question
        self.current_date = current_date
        self.timezone = timezone

    def _validate_finish(self, call, assignment, tools) -> ResearcherResult | None:
        if call["name"] != "finish_research":
            return None
        try:
            result = ResearcherResult.model_validate(call["args"])
        except ValidationError:
            return None
        if result.task_id != assignment.id:
            return None
        claimed = set(result.source_urls)
        if not claimed <= set(tools.read_sources):
            return None
        if result.status == "completed" and not claimed:
            return None
        return result

    @staticmethod
    def _fallback(assignment, tools, reason: str) -> ResearcherResult:
        has_sources = bool(tools.read_sources)
        return ResearcherResult(
            task_id=assignment.id,
            status="partial" if has_sources else "blocked",
            summary=(
                "已取得部分相关原文，但研究员未能完成结构化收尾。"
                if has_sources
                else "未取得可用于当前任务的已读原文。"
            ),
            source_urls=sorted(tools.read_sources),
            gaps=[f"{item}：未确认" for item in assignment.required_outputs],
            stop_reason=reason,
        )

    async def run(self, assignment, tools) -> ResearcherResult:
        normal_bound = self.model.bind_tools([*RESEARCHER_MODEL_TOOLS, FINISH_TOOL])
        research_tool_names = {
            tool["function"]["name"] for tool in RESEARCHER_MODEL_TOOLS
        }
        base = researcher_messages(
            self.question,
            assignment,
            current_date=self.current_date,
            timezone=self.timezone,
        )
        turns: list[list] = []
        researched_outputs: set[str] = set()
        rounds = int(
            getattr(self.runtime.settings, "multi_agent_max_researcher_rounds", 3)
        )
        normal_rounds = max(1, rounds - 1)

        for round_index in range(normal_rounds):
            messages = base + [message for turn in turns[-2:] for message in turn]
            messages.append(
                HumanMessage(
                    content=json.dumps(
                        {
                            "research_decision": (
                                f"{round_index + 1}/{normal_rounds}"
                            ),
                            "local_network_attempts_remaining": max(
                                0, tools.lease.limit - tools.lease.used
                            ),
                            "not_yet_researched_outputs": [
                                output
                                for output in assignment.required_outputs
                                if output not in researched_outputs
                            ],
                            "researched_outputs": [
                                output
                                for output in assignment.required_outputs
                                if output in researched_outputs
                            ],
                            "instruction": (
                                "Finish as soon as the required outputs are supported; "
                                "otherwise use one tool for a material missing output."
                            ),
                        },
                        ensure_ascii=False,
                    )
                )
            )
            try:
                response = await self.runtime.invoke(
                    normal_bound, messages, "researcher"
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - Provider failures become task-local state
                return self._fallback(assignment, tools, "provider_failure")
            calls = getattr(response, "tool_calls", [])
            if len(calls) == 1:
                result = self._validate_finish(calls[0], assignment, tools)
                if result is not None:
                    return result
            if not calls or any(
                call["name"] == "finish_research" for call in calls
            ):
                turns.append(
                    [HumanMessage(content="Choose valid research tools or finish_research.")]
                )
                continue
            if any(call["name"] not in research_tool_names for call in calls):
                turns.append(
                    [HumanMessage(content="Choose one available research tool.")]
                )
                continue
            if len(calls) > 1:
                self.runtime.emit(
                    "tool.batch_limited",
                    f"{assignment.id} 单轮只执行第一个研究工具",
                    task_id=assignment.id,
                    requested=len(calls),
                    executed=1,
                )
                calls = calls[:1]

            call = calls[0]
            target_output = call.get("args", {}).get("target_output")
            if target_output not in assignment.required_outputs:
                safe_target = (
                    target_output if isinstance(target_output, str) else ""
                )
                self.runtime.emit(
                    "tool.rejected",
                    f"{assignment.id} 工具调用未绑定有效检查项",
                    task_id=assignment.id,
                    tool=call["name"],
                    target_output=safe_target,
                    reason_code="unknown_target_output",
                )
                turns.append(
                    [
                        AIMessage(
                            content=response.content or "",
                            tool_calls=[call],
                        ),
                        ToolMessage(
                            content=json.dumps(
                                {
                                    "ok": False,
                                    "error": "unknown_target_output",
                                    "allowed_target_outputs": list(
                                        assignment.required_outputs
                                    ),
                                },
                                ensure_ascii=False,
                            ),
                            tool_call_id=call["id"],
                        ),
                    ]
                )
                continue

            async def run_tool(call, target_output=target_output):
                started = time.monotonic()
                self.runtime.emit(
                    "tool.started",
                    f"{assignment.id} 针对检查项「{target_output}」"
                    f"调用 {call['name']}："
                    + json.dumps(call["args"], ensure_ascii=False)[:300],
                    task_id=assignment.id,
                    tool=call["name"],
                    target_output=target_output,
                )
                timeout = float(
                    getattr(
                        self.runtime.settings,
                        "multi_agent_call_timeout_seconds",
                        45,
                    )
                )
                try:
                    result = await asyncio.wait_for(
                        tools.execute(call["name"], call["args"]),
                        timeout=timeout,
                    )
                except TimeoutError:
                    result = {"ok": False, "error": "tool_timeout"}
                self.runtime.emit(
                    "tool.completed",
                    f"{assignment.id} {call['name']} "
                    + ("完成" if result.get("ok") else "失败：" + result.get("error", "unknown")),
                    task_id=assignment.id,
                    tool=call["name"],
                    ok=bool(result.get("ok")),
                    cached=bool(result.get("cached")),
                    elapsed_seconds=round(time.monotonic() - started, 3),
                )
                return result

            results = await asyncio.gather(*(run_tool(call) for call in calls))
            for current_call, result in zip(calls, results, strict=True):
                if result.get("ok"):
                    researched_outputs.add(
                        current_call["args"]["target_output"]
                    )
            history_response = AIMessage(
                content=response.content or "",
                tool_calls=calls,
            )
            turns.append(
                [
                    history_response,
                    *[
                        ToolMessage(
                            content=json.dumps(result, ensure_ascii=False),
                            tool_call_id=call["id"],
                        )
                        for call, result in zip(calls, results, strict=True)
                    ],
                ]
            )

        closeout_bound = self.model.bind_tools([FINISH_TOOL])
        messages = base + [message for turn in turns[-2:] for message in turn]
        messages.append(
            HumanMessage(
                content=(
                    "This is the reserved final decision. Do not research further. Return "
                    "exactly one finish_research call. Re-read the latest tool observations, "
                    "cite only this task's actually read URLs, and list each material required "
                    "output that remains unconfirmed."
                )
            )
        )
        try:
            response = await self.runtime.invoke(closeout_bound, messages, "researcher")
            calls = getattr(response, "tool_calls", [])
            if len(calls) == 1:
                result = self._validate_finish(calls[0], assignment, tools)
                if result is not None:
                    return result
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - malformed/provider closeout is recoverable
            return self._fallback(assignment, tools, "finalization_failed")
        return self._fallback(assignment, tools, "finalization_failed")
