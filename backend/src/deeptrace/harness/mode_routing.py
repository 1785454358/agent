"""One budgeted semantic assessment, followed by host-owned strategy selection."""

from __future__ import annotations

import logging

from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from deeptrace.domain import ResearchMode
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.model_budget import BudgetStateUnavailable
from deeptrace.harness.model_io import payload_text
from deeptrace.harness.prompts import task_messages
from deeptrace.harness.state import HarnessState
from deeptrace.observability.progress import emit_progress


class TaskProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dependent_steps: bool = Field(strict=True)
    independent_tracks: int = Field(strict=True, ge=0, le=6)
    reason: str = Field(min_length=1, max_length=300)


def mode_for_profile(profile: TaskProfile) -> ResearchMode:
    if profile.dependent_steps:
        return ResearchMode.PLAN_EXECUTE
    if profile.independent_tracks >= 2:
        return ResearchMode.MULTI_AGENT
    return ResearchMode.WORKFLOW


async def select_research_mode(state: HarnessState, runtime: Runtime[HarnessContext]) -> dict:
    turn = dict(state["turn"])
    requested = turn.get("requested_mode", turn["selected_mode"])
    action = "manual"
    if requested != "auto":
        selected = ResearchMode(requested)
        reason = "按指定研究模式执行。"
    else:
        summary = state["conversation"]["summary"]
        recent = "\n".join(str(message.content)[:400] for message in state["conversation"]["messages"][-4:])
        try:
            response = await runtime.context.model_gateway.invoke(
                role="router",
                messages=task_messages(
                    instruction="分析用户任务的执行特点，只输出指定 JSON，不执行研究，不回答问题。",
                    task=turn["user_input"], constraints=summary.user_constraints[:6],
                    prompt=(
                        "判断任务特点，简短说明选择依据，不输出推理过程。\n"
                        '仅输出 {"dependent_steps":true或false,'
                        '"independent_tracks":0到6的整数,"reason":"不超过100字的中文说明"}。\n'
                        "范围明确的单一查询、文档解释、同一资料内有限对比属于单一研究方向。"
                        "同一问题的多个查询词、同一文档内两个API的简单比较不等于多个独立研究方向。\n"
                        "dependent_steps：必须先得到前一步结果才能确定后一步的行动，例如先诊断"
                        "根因再制定并验证方案、根据阶段结果迭代。列举回答章节不属于执行依赖。\n"
                        "independent_tracks：可由不同研究员独立取材并最终汇总的实质研究方向数，"
                        "如跨领域、多技术路线、多地区的独立调查。\n"
                        "宿主选择规则：有执行依赖→Plan-and-Execute；否则至少两个实质独立方向"
                        "→Multi-Agent；其余→Workflow。明确限定了范围的多方向调查仍可并行，"
                        "不能仅因目标描述清楚就当作单一资料查询。"
                        "优先选择能充分完成任务的简单策略，不因长问题或出现比较一词就选多智能体。\n"
                        f"会话主题：{summary.topic[:400]}\n最近对话（仅作背景）：\n{recent}"
                    ),
                ),
            )
            profile = TaskProfile.model_validate_json(payload_text(response))
            selected = mode_for_profile(profile)
            reason = profile.reason
            action = "automatic"
        except BudgetStateUnavailable:
            raise
        except Exception as exc:
            logging.getLogger(__name__).warning("Mode classification unavailable: %s", type(exc).__name__)
            selected = ResearchMode.WORKFLOW
            reason = "自动分类暂不可用，采用 Workflow 处理本次任务。"
            action = "fallback"
    turn["selected_mode"] = selected
    turn["routing_reason"] = reason
    await emit_progress(runtime.context, "research.routed", mode=selected.value, reason=reason, action=action)
    return {"turn": turn, "conversation": {"active_mode": selected}}
