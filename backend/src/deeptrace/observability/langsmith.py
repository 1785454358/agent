"""Serialization boundaries for native LangSmith instrumentation.

LangGraph and LangChain provide node and model spans; no local trace storage.
"""
from langsmith.run_helpers import get_current_run_tree


def application_inputs(inputs):
    request = inputs["request"]
    return {"question": request.question, "run_id": request.run_id,
            "thread_id": request.thread_id, "mode": str(request.mode)}


def application_outputs(result):
    if result is None:  # The SDK invokes output processors on exception paths too.
        return {}
    return {"answer": result.response_outcome.content if result.response_outcome else "",
            "status": result.status, "finish_reason": result.finish_reason.value,
            "research_sufficiency": result.research_sufficiency.value,
            "executed_steps": result.executed_steps, "sources": result.sources}


def tool_inputs(inputs):
    request = inputs.get("request")
    # Malformed requests still reach the original gateway validation.
    if not hasattr(request, "tool"):
        return {"invalid_request": True}
    allowed = {"query", "url", "limit", "evidence_id", "max_chars", "start_char",
               "end_char", "search_depth", "include_domains", "exclude_domains",
               "topic", "time_range", "start_date", "end_date", "path", "pattern",
               "start", "find", "after"}
    return {"tool": request.tool.value, "arguments": {
                key: value for key, value in request.arguments.items() if key in allowed},
            "run_id": request.run_id, "call_id": request.call_id}


def tool_outputs(result):
    if result is None:
        return {}
    return {"ok": result.ok, "cached": result.cached, "replayed": result.replayed,
            "error_code": result.error_code}


def annotate_tool_result(result):
    tree = get_current_run_tree()
    if tree is not None:
        tree.add_metadata(tool_outputs(result))
        if not result.ok:
            tree.error = result.error_code or "tool_error"
    return result
