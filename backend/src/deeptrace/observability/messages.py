"""Human-readable run event messages for dashboards and SSE consumers."""

from __future__ import annotations

from typing import Any

# Public primitive fields only: never copy arbitrary model/provider payloads.
_PUBLIC_FIELDS = frozenset({
    "tool", "call_id", "caller_id", "mode", "ok", "error_code",
    "error_category", "retryable", "message", "cached", "replayed", "duration_ms",
    "round", "task", "tasks_json", "gaps_json", "reason", "action", "next_step",
    "url", "query", "branch", "iteration", "covered", "total",
})


def public_event_details(payload: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    fields = dict(payload)
    # Agent observations include preflight denials and cache hits which never
    # emitted gateway started/completed events. Keep just their public outcome.
    result = payload.get("result")
    if isinstance(result, dict):
        fields.update({key: result[key] for key in (
            "ok", "error_code", "error_category", "retryable", "message", "cached", "replayed"
        ) if key in result})
    if "call_id" not in fields and isinstance(payload.get("tool_call_id"), str):
        fields["call_id"] = payload["tool_call_id"]
    return {
        key: value for key, value in fields.items()
        if key in _PUBLIC_FIELDS and isinstance(value, (str, int, float, bool, type(None)))
    }

_TOOL_LABEL: dict[str, str] = {
    "search_web": "网页搜索",
    "fetch_page": "网页抓取",
    "search_memory": "记忆检索",
    "read_evidence": "阅读原文证据",
}

_PHASE_LABEL: dict[str, str] = {
    "run.started": "研究任务开始",
    "planning.started": "开始规划研究策略",
    "planning.completed": "研究计划已生成",
    "replanning.started": "开始调整研究计划",
    "replanning.completed": "研究计划调整完成",
    "plan.finish_rejected": "计划评估未通过，继续补查",
    "task.started": "开始执行子任务",
    "task.completed": "子任务执行结束",
    "task.failed": "子任务执行失败",
    "evaluation.started": "开始核对本轮证据",
    "evaluation.completed": "本轮证据核对结束",
    "research.batch_synthesis.started": "开始整理研究发现",
    "research.batch_synthesis.completed": "研究发现已整理",
    "research.batch_synthesis.failed": "研究发现待核验",
    "research.route": "确定后续研究步骤",
    "agent.context_view": "准备研究上下文",
    "evidence.view": "整理原文证据片段",
    "supervisor.dispatched": "Supervisor 已派发研究方向",
    "supervisor.retry": "Supervisor 发起补查",
    "supervisor.fallback": "Supervisor 启用兜底策略",
    "supervisor.reviewed": "Supervisor 完成结果评审",
    "researcher.queued": "Researcher 排队等待执行",
    "researcher.started": "Researcher 开始研究",
    "researcher.completed": "Researcher 完成研究",
    "tool.batch_limited": "并发工具调用已限流",
    "research.completed": "资料收集完成，开始整理回答",
    "writing.started": "开始撰写回答",
    "writing.completed": "回答撰写完成",
    "response.budget": "回答上下文超出预算，已按优先级裁剪",
    "response.truncated": "回答输出被调整，已重试或按句截断",
    "run.completed": "研究已完成",
    "response.completed": "研究已完成",
}


def humanize_event_message(event_type: str, payload: dict[str, Any]) -> str:
    """Produce a readable message: retry/error first, then tool name, then phase."""
    tool = payload.get("tool")
    label = _TOOL_LABEL.get(tool, tool) if isinstance(tool, str) and tool else ""
    if event_type == "tool.retry":
        return f"{label}调用失败，正在重试…" if label else "工具调用失败，正在重试…"
    error_code = payload.get("error_code")
    if error_code:
        prefix = f"{label}失败" if label else "工具调用失败"
        return f"{prefix}（{error_code}）"
    if label:
        if event_type == "tool.started":
            return f"正在{label}…"
        if event_type == "tool.completed":
            return f"{label}完成" if payload.get("ok", True) else f"{label}失败"
    return _PHASE_LABEL.get(event_type, event_type)
