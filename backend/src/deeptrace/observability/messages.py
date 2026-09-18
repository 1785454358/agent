"""Human-readable run event messages for dashboards and SSE consumers."""

from __future__ import annotations

from typing import Any

_TOOL_LABEL: dict[str, str] = {
    "search_web": "网页搜索",
    "fetch_page": "网页抓取",
    "search_memory": "记忆检索",
}

_PHASE_LABEL: dict[str, str] = {
    "run.started": "研究任务开始",
    "planning.started": "开始规划研究策略",
    "planning.completed": "研究计划已生成",
    "replanning.started": "开始调整研究计划",
    "replanning.completed": "研究计划调整完成",
    "plan.finish_rejected": "计划评估未通过，继续补查",
    "task.started": "开始执行子任务",
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
