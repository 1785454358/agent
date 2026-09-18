"""Tool protocol and dependency-aware dispatch through ToolGateway."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from deeptrace.domain import (
    ErrorCategory,
    ErrorRecord,
    ResearchMode,
    ResearchTopicInput,
    ToolName,
    ToolRequest,
    ToolResult,
    TopicStepError,
)
from deeptrace.harness.agent_state import (
    AgentTodo,
    TodoStatus,
    WriteTodosArguments,
    topic_input,
)
from deeptrace.tools.adapters import FetchPageArguments, SearchWebArguments
from deeptrace.tools.policy import (
    CallerRole,
    ToolCaller,
    UrlAuthorization,
    UrlAuthorizationSource,
)
from deeptrace.tools.scraper.urls import normalize_url_before_fetch, validate_public_url

WRITE_TODOS_TOOL = "write_todos"
MAX_TOOL_MESSAGE_CHARS = 4_000
MAX_DISCOVERY_BODY_CHARS = 20_000
RESEARCH_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": WRITE_TODOS_TOOL,
            "description": (
                "创建或更新研究计划。每次调用提交完整的计划列表，用 status "
                "标记每项进度（pending / in_progress / completed）。"
                "所有项完成前不得结束研究。"
            ),
            "parameters": WriteTodosArguments.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": ToolName.SEARCH_WEB.value,
            "description": (
                "使用搜索引擎检索网页，返回标题、URL 与摘要。用它来发现资料来源。"
            ),
            "parameters": SearchWebArguments.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": ToolName.FETCH_PAGE.value,
            "description": (
                "抓取一个网页的正文并登记为可引用证据。url 必须是搜索结果或"
                "已抓取页面中出现过的公网 URL。"
            ),
            "parameters": FetchPageArguments.model_json_schema(),
        },
    },
)

_URL_PATTERN = re.compile(r"https?://[^\s\"'<>)\]}]+")

_ROLE_BY_MODE: dict[ResearchMode, CallerRole] = {
    ResearchMode.WORKFLOW: CallerRole.WORKFLOW_GRAPH,
    ResearchMode.PLAN_EXECUTE: CallerRole.PLAN_EXECUTE_EXECUTOR,
    ResearchMode.MULTI_AGENT: CallerRole.MULTI_AGENT_RESEARCHER,
}

_STAGE_BY_TOOL: dict[ToolName, str] = {
    ToolName.SEARCH_WEB: "search",
    ToolName.FETCH_PAGE: "fetch",
}


def _caller(topic_input: ResearchTopicInput) -> ToolCaller:
    return ToolCaller(
        caller_id=topic_input.caller_id,
        role=_ROLE_BY_MODE[topic_input.mode],
        mode=topic_input.mode,
    )


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _request_id(topic_input: ResearchTopicInput) -> str:
    return "request-" + _digest(
        f"agent_executor\0{topic_input.thread_id}\0{topic_input.run_id}\0{topic_input.mode}\0{topic_input.caller_id}\0{topic_input.query}"
    )


def _tool_result_message(tool: ToolName, result: ToolResult) -> str:
    payload: dict[str, Any]
    if result.ok:
        payload = {
            "ok": True,
            "tool": tool.value,
            "preview": result.preview[:MAX_TOOL_MESSAGE_CHARS],
            "evidence_ids": list(result.evidence_ids),
        }
    else:
        payload = {
            "ok": False,
            "tool": tool.value,
            "error_code": result.error_code,
            "error_category": (
                None if result.error_category is None else result.error_category.value
            ),
            "retryable": result.retryable,
            "message": result.message,
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _unknown_tool_message(name: str) -> str:
    return json.dumps(
        {
            "ok": False,
            "tool": name,
            "error_code": "tool_not_registered",
            "error_category": "policy",
            "retryable": False,
            "message": "该工具不可用，请改用 search_web 或 fetch_page。",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _invalid_todos_message() -> str:
    return json.dumps(
        {
            "ok": False,
            "tool": WRITE_TODOS_TOOL,
            "error_code": "invalid_arguments",
            "error_category": "validation",
            "retryable": False,
            "message": (
                "write_todos 需要 1-20 项，每项包含 content 与 status"
                "（pending / in_progress / completed）。"
            ),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _todos_tool_message(todos: list[AgentTodo]) -> str:
    completed = sum(1 for todo in todos if todo.status == TodoStatus.COMPLETED)
    return json.dumps(
        {
            "ok": True,
            "tool": WRITE_TODOS_TOOL,
            "todos": [todo.model_dump(mode="json") for todo in todos],
            "completed": completed,
            "total": len(todos),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _urls_from_search_preview(preview: str) -> list[str]:
    try:
        payload = json.loads(preview)
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    urls: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        try:
            normalized = normalize_url_before_fetch(url)
        except (TypeError, ValueError):
            continue
        safe, _reason = validate_public_url(normalized)
        if safe and normalized not in urls:
            urls.append(normalized)
    return urls


def _urls_from_body(body: str, *, limit: int) -> list[str]:
    urls: list[str] = []
    for match in _URL_PATTERN.findall(body[:MAX_DISCOVERY_BODY_CHARS]):
        try:
            normalized = normalize_url_before_fetch(match)
        except (TypeError, ValueError):
            continue
        safe, _reason = validate_public_url(normalized)
        if not safe or normalized in urls:
            continue
        urls.append(normalized)
        if len(urls) >= limit:
            break
    return urls


@dataclass
class Observation:
    message: ToolMessage
    result: ToolResult | None = None
    urls: list[str] = field(default_factory=list)
    error: ErrorRecord | None = None
    todos: list[AgentTodo] | None = None


def failure(code, *, source="tool", category=ErrorCategory.FATAL):
    return ErrorRecord(
        code=code,
        category=category,
        source=source,
        node="execute_tools",
        public_message=code,
    )


def skipped(call, code):
    return Observation(
        ToolMessage(
            tool_call_id=call["id"],
            content=json.dumps(
                {"ok": False, "error_code": code, "message": "调用未执行：" + code}
            ),
        ),
        error=failure(
            code,
            category=ErrorCategory.CANCELLED
            if code == "cancelled"
            else ErrorCategory.POLICY,
        ),
    )


async def execute_batch(state, context, *, max_concurrency=4, max_discovered_urls=200):
    task = topic_input(state)
    calls = list(state["messages"][-1].tool_calls)
    observations = {}
    seen = list(state.get("seen_urls") or [])
    pages = state.get("pages_fetched", 0)
    stopped = ""

    async def invoke(index):
        call = calls[index]
        name, args, identity = call["name"], call.get("args") or {}, call["id"]
        if name == WRITE_TODOS_TOOL:
            try:
                todos = WriteTodosArguments.model_validate(args).todos
                return Observation(
                    ToolMessage(
                        content=_todos_tool_message(todos), tool_call_id=identity
                    ),
                    todos=todos,
                )
            except ValidationError:
                return Observation(
                    ToolMessage(
                        content=_invalid_todos_message(), tool_call_id=identity
                    ),
                    error=failure(
                        "invalid_arguments", category=ErrorCategory.VALIDATION
                    ),
                )
        if name not in {ToolName.SEARCH_WEB.value, ToolName.FETCH_PAGE.value}:
            return Observation(
                ToolMessage(content=_unknown_tool_message(name), tool_call_id=identity),
                error=failure("tool_not_registered", category=ErrorCategory.POLICY),
            )
        try:
            tool = ToolName(name)
            request = ToolRequest(
                request_id=_request_id(task),
                run_id=task.run_id,
                thread_id=task.thread_id,
                call_id=_digest(_request_id(task) + "\0" + identity),
                tool=tool,
                arguments=args,
            )
            authorization = (
                UrlAuthorization(
                    source=UrlAuthorizationSource.AGENT_DISCOVERED, urls=frozenset(seen)
                )
                if tool == ToolName.FETCH_PAGE and seen
                else None
            )
            result = await context.tool_gateway.execute(
                tenant_id=context.workspace_id,
                caller=_caller(task),
                request=request,
                authorization=authorization,
            )
            observation = Observation(
                ToolMessage(
                    content=_tool_result_message(tool, result), tool_call_id=identity
                ),
                result=result,
            )
            if not result.ok:
                observation.error = failure(
                    result.error_code or "tool_internal_error",
                    category=result.error_category,
                )
            elif tool == ToolName.SEARCH_WEB:
                observation.urls = _urls_from_search_preview(result.preview)
            elif result.evidence_ids:
                try:
                    body = await context.evidence_store.read_body(
                        context.workspace_id, result.evidence_ids[0]
                    )
                    observation.urls = _urls_from_body(body, limit=max_discovered_urls)
                except Exception:
                    logging.getLogger(__name__).warning(
                        "Optional link discovery unavailable", exc_info=True
                    )
            return observation
        except asyncio.CancelledError:
            return skipped(call, "cancelled")
        except Exception:
            logging.getLogger(__name__).exception(
                "Agent tool boundary failed: %s", identity
            )
            return Observation(
                ToolMessage(
                    content=json.dumps(
                        {"ok": False, "error_code": "tool_internal_error"}
                    ),
                    tool_call_id=identity,
                ),
                error=failure("tool_internal_error"),
            )

    # Searches discover authorization for fetches in this batch. Already
    # authorized fetches may share a wave with searches. Local writes are ordered.
    pending = list(range(len(calls)))
    while pending:
        if stopped:
            for index in pending:
                observations[index] = skipped(calls[index], stopped)
            break
        ready = [
            i
            for i in pending
            if calls[i]["name"] != ToolName.FETCH_PAGE.value
            or calls[i].get("args", {}).get("url") in seen
        ]
        if not ready:
            ready = pending[:1]  # gateway returns an authorization error
        if calls[ready[0]]["name"] == WRITE_TODOS_TOOL:
            ready = ready[:1]
        else:
            ready = [i for i in ready if calls[i]["name"] != WRITE_TODOS_TOOL][
                :max_concurrency
            ]
        slots = task.max_pages - pages
        wave = []
        for index in ready:
            if calls[index]["name"] == ToolName.FETCH_PAGE.value:
                if slots <= 0:
                    observations[index] = skipped(calls[index], "page_limit")
                    pending.remove(index)
                    continue
                slots -= 1
            wave.append(index)
        if not wave:
            continue
        jobs = [asyncio.create_task(invoke(index)) for index in wave]
        try:
            results = await asyncio.gather(*jobs)
        except asyncio.CancelledError:
            for job in jobs:
                job.cancel()
            settled = await asyncio.gather(*jobs, return_exceptions=True)
            results = [
                r if isinstance(r, Observation) else skipped(calls[i], "cancelled")
                for i, r in zip(wave, settled)
            ]
            stopped = "cancelled"
        for index, observation in zip(wave, results):
            observations[index] = observation
            pending.remove(index)
            for url in observation.urls:
                if url not in seen and len(seen) < max_discovered_urls:
                    seen.append(url)
            if (
                observation.result
                and observation.result.ok
                and calls[index]["name"] == ToolName.FETCH_PAGE.value
            ):
                pages += 1
            error = observation.error
            if error:
                if error.category == ErrorCategory.CANCELLED:
                    stopped = "cancelled"
                elif error.code == "budget_exhausted" and stopped != "cancelled":
                    stopped = "budget_exhausted"
                elif error.category == ErrorCategory.FATAL and not stopped:
                    stopped = "tool_error"

    evidence, attempted, errors = [], [], []
    failures = list(state.get("failures") or [])
    todos = list(state.get("todos") or [])
    consecutive = state.get("consecutive_errors", 0)
    for index in range(len(calls)):
        observation = observations[index]
        call = calls[index]
        if observation.todos is not None:
            todos = observation.todos
        if observation.error:
            failures.append(observation.error)
            consecutive += 1
            if call["name"] in (ToolName.SEARCH_WEB.value, ToolName.FETCH_PAGE.value):
                errors.append(
                    TopicStepError(
                        stage="search"
                        if call["name"] == ToolName.SEARCH_WEB.value
                        else "fetch",
                        target=str(call.get("args", {}).get("url", ""))[:2000],
                        code=observation.error.code,
                    )
                )
        elif observation.result and observation.result.ok:
            consecutive = 0
        if observation.result:
            evidence.extend(observation.result.evidence_ids)
            if call["name"] == ToolName.FETCH_PAGE.value:
                url = call.get("args", {}).get("url")
                if isinstance(url, str) and url.strip() and len(url.strip()) <= 2048:
                    attempted.append(url.strip())
    return {
        "messages": [observations[i].message for i in range(len(calls))],
        "todos": todos,
        "evidence_ids": evidence,
        "attempted_urls": attempted,
        "errors": errors,
        "failures": failures[-100:],
        "seen_urls": seen,
        "executed_steps": len(calls),
        "pages_fetched": pages,
        "consecutive_errors": consecutive,
        "stop_reason": stopped,
    }
