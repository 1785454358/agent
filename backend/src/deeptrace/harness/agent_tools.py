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
from deeptrace.domain.evidence import Finding
from deeptrace.domain.evidence_anchor import merge_read_anchors
from deeptrace.domain.execution import RequestBudgetExceeded
from deeptrace.harness.agent_state import (
    AgentTodo,
    TodoStatus,
    WriteTodosArguments,
    topic_input,
)
from deeptrace.harness.read_anchors import capture_read_anchors
from deeptrace.harness.research_completion import (
    FinishResearchArguments,
    validate_completion,
)
from deeptrace.harness.research_findings import (
    RecordFindingsArguments,
    number_read_preview,
    resolve_recorded_findings,
)
from deeptrace.tools.adapters import FetchPageArguments, SearchWebArguments
from deeptrace.tools.evidence_read import ReadEvidenceArguments
from deeptrace.tools.policy import (
    CallerRole,
    EvidenceAuthorization,
    ToolCaller,
    UrlAuthorization,
    UrlAuthorizationSource,
)
from deeptrace.tools.scraper.urls import normalize_url_before_fetch, validate_public_url

WRITE_TODOS_TOOL = "write_todos"
RECORD_FINDINGS_TOOL = "record_findings"
FINISH_RESEARCH_TOOL = "finish_research"
LOCAL_TOOLS = frozenset({WRITE_TODOS_TOOL, RECORD_FINDINGS_TOOL, FINISH_RESEARCH_TOOL})
MAX_TOOL_MESSAGE_CHARS = 4_000
MAX_DISCOVERY_BODY_CHARS = 20_000
RESEARCH_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": FINISH_RESEARCH_TOOL,
            "description": (
                "申请完成本分支，summary概括已有发现和边界；不代表全局答案已充分。"
                "须有仍有效的实际已读原文且已有todo全部完成。可在可选record_findings和write_todos"
                "之后同批最后调用；不可与search/fetch/read混批。失败时保留缺口。"
            ),
            "parameters": FinishResearchArguments.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": RECORD_FINDINGS_TOOL,
            "description": (
                "保存已阅读的关键发现。每项给出 claim、之前 read_evidence 返回的 n 短引用 refs "
                "和 confidence。只保存有原文支持的事实，不接受同批尚未返回的引用。"
                "这些是待评估的发现，不表示答案要点已覆盖。"
            ),
            "parameters": RecordFindingsArguments.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": WRITE_TODOS_TOOL,
            "description": (
                "创建或更新研究计划。每次调用提交完整的计划列表，用 status "
                "标记每项进度（pending / in_progress / completed）。"
                "仅在初始化、已观察到的进度或计划变化时更新；计划未变化时不要重复提交。"
                "可与下一步研究工具同批调用；不能把同批尚未返回的工具请求提前标为 completed。"
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
    {
        "type": "function",
        "function": {
            "name": ToolName.READ_EVIDENCE.value,
            "description": (
                "读取本分支已抓取或父任务授权证据的原文。使用已授权的 evidence_id，"
                "可按 query 选段，或用 find 定位原文字符串、after 继续查找，或用 start 读取字符范围；"
                "三种选择方式互斥。返回可供 record_findings 使用的 n 短引用。"
                "未指定选择方式时按当前研究查询读取。"
            ),
            "parameters": ReadEvidenceArguments.model_json_schema(),
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
    ToolName.READ_EVIDENCE: "read",
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
    research_findings: list[Finding] | None = None
    completion_summary: str | None = None


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
    stopped = state.get("stop_reason") or ""
    references = dict(state.get("research_refs") or {})
    batch_references = dict(references)
    recorded = list(state.get("research_findings") or [])
    effective_todos = list(state.get("todos") or [])
    invoked = set()

    async def invoke(index):
        invoked.add(index)
        call = calls[index]
        name, args, identity = call["name"], call.get("args") or {}, call["id"]
        if name == FINISH_RESEARCH_TOOL:
            try:
                arguments = FinishResearchArguments.model_validate(args)
                if (
                    index != len(calls) - 1
                    or sum(c["name"] == FINISH_RESEARCH_TOOL for c in calls) != 1
                    or any(c["name"] not in LOCAL_TOOLS for c in calls)
                ):
                    raise ValueError("invalid_finish_batch")
                if any(o.error is not None for o in observations.values()):
                    raise ValueError("finish_prior_call_failed")
                granted_task = task.model_copy(
                    update={
                        "authorized_evidence_ids": list(
                            dict.fromkeys(
                                [
                                    *task.authorized_evidence_ids,
                                    *(state.get("evidence_ids") or []),
                                ]
                            )
                        )
                    }
                )
                await validate_completion(
                    read_anchors=state.get("read_anchors") or [],
                    task=granted_task,
                    findings=recorded,
                    todos=effective_todos,
                    context=context,
                )
                return Observation(
                    ToolMessage(
                        tool_call_id=identity,
                        content=json.dumps(
                            {
                                "ok": True,
                                "tool": name,
                                "summary": arguments.summary,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                    completion_summary=arguments.summary,
                )
            except asyncio.CancelledError:
                return skipped(call, "cancelled")
            except (ValidationError, ValueError) as exc:
                code = (
                    "invalid_arguments"
                    if isinstance(exc, ValidationError)
                    else str(exc)
                )
                return Observation(
                    ToolMessage(
                        tool_call_id=identity,
                        content=json.dumps(
                            {
                                "ok": False,
                                "tool": name,
                                "error_code": code,
                            }
                        ),
                    ),
                    error=failure(code, category=ErrorCategory.VALIDATION),
                )
            except Exception:
                logging.getLogger(__name__).exception("Research completion failed")
                return Observation(
                    ToolMessage(
                        tool_call_id=identity,
                        content=json.dumps(
                            {
                                "ok": False,
                                "tool": name,
                                "error_code": "tool_internal_error",
                            }
                        ),
                    ),
                    error=failure("tool_internal_error"),
                )
        if name == RECORD_FINDINGS_TOOL:
            try:
                arguments = RecordFindingsArguments.model_validate(args)
                granted_task = task.model_copy(
                    update={
                        "authorized_evidence_ids": list(
                            dict.fromkeys(
                                [
                                    *task.authorized_evidence_ids,
                                    *(state.get("evidence_ids") or []),
                                ]
                            )
                        )
                    }
                )
                findings = await resolve_recorded_findings(
                    arguments,
                    task=granted_task,
                    references=batch_references,
                    existing=recorded,
                    context=context,
                )
                return Observation(
                    ToolMessage(
                        tool_call_id=identity,
                        content=json.dumps(
                            {
                                "ok": True,
                                "tool": name,
                                "recorded_ids": [f.id for f in findings],
                                "total": len(findings),
                            }
                        ),
                    ),
                    research_findings=findings,
                )
            except asyncio.CancelledError:
                return skipped(call, "cancelled")
            except (ValidationError, ValueError) as exc:
                code = (
                    "invalid_arguments"
                    if isinstance(exc, ValidationError)
                    else str(exc)
                )
                return Observation(
                    ToolMessage(
                        tool_call_id=identity,
                        content=json.dumps(
                            {
                                "ok": False,
                                "tool": name,
                                "error_code": code,
                            }
                        ),
                    ),
                    error=failure(code, category=ErrorCategory.VALIDATION),
                )
            except Exception:
                logging.getLogger(__name__).exception("Finding recording failed")
                return Observation(
                    ToolMessage(
                        tool_call_id=identity,
                        content=json.dumps(
                            {
                                "ok": False,
                                "tool": name,
                                "error_code": "tool_internal_error",
                            }
                        ),
                    ),
                    error=failure("tool_internal_error"),
                )
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
        if name not in {
            ToolName.SEARCH_WEB.value,
            ToolName.FETCH_PAGE.value,
            ToolName.READ_EVIDENCE.value,
        }:
            return Observation(
                ToolMessage(content=_unknown_tool_message(name), tool_call_id=identity),
                error=failure("tool_not_registered", category=ErrorCategory.POLICY),
            )
        try:
            tool = ToolName(name)
            evidence_options = {}
            if tool is ToolName.READ_EVIDENCE:
                args = dict(args)
                if all(args.get(key) is None for key in ("query", "start", "find")):
                    args["query"] = task.query
                evidence_options["evidence_authorization"] = EvidenceAuthorization(
                    evidence_ids=frozenset(
                        [
                            *(state.get("evidence_ids") or []),
                            *task.authorized_evidence_ids,
                        ]
                    )
                )
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
                **evidence_options,
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
            elif tool is ToolName.FETCH_PAGE and result.evidence_ids:
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
        except RequestBudgetExceeded:
            return Observation(
                ToolMessage(
                    content=json.dumps({"ok": False, "error_code": "budget_exhausted"}),
                    tool_call_id=identity,
                ),
                error=failure("budget_exhausted", category=ErrorCategory.PARTIAL),
            )
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
        if calls[ready[0]]["name"] in LOCAL_TOOLS:
            ready = ready[:1]
        else:
            ready = [i for i in ready if calls[i]["name"] not in LOCAL_TOOLS][
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
            if observation.research_findings is not None:
                recorded = observation.research_findings
            if observation.todos is not None:
                effective_todos = observation.todos
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
    anchors = list(state.get("read_anchors") or [])
    read_diagnostics = list(state.get("read_anchor_diagnostics") or [])
    finding_diagnostics = list(state.get("research_finding_diagnostics") or [])
    failures = list(state.get("failures") or [])
    todos = list(state.get("todos") or [])
    consecutive = state.get("consecutive_errors", 0)
    for index in range(len(calls)):
        observation = observations[index]
        call = calls[index]
        if call["name"] in LOCAL_TOOLS:
            try:
                await context.event_sink.emit(
                    "agent.local_tool",
                    {
                        "run_id": task.run_id,
                        "caller_id": task.caller_id,
                        "query": task.query,
                        "call_id": call["id"],
                        "tool": call["name"],
                        "executed": index in invoked,
                        "ok": observation.error is None,
                        "error_code": observation.error.code
                        if observation.error
                        else None,
                    },
                )
            except Exception:
                logging.getLogger(__name__).warning(
                    "Local-tool telemetry unavailable", exc_info=True
                )
        if observation.todos is not None:
            todos = observation.todos
        if observation.error:
            failures.append(observation.error)
            consecutive += 1
            if call["name"] in _STAGE_BY_TOOL:
                errors.append(
                    TopicStepError(
                        stage=_STAGE_BY_TOOL[ToolName(call["name"])],
                        target=str(
                            call.get("args", {}).get(
                                "evidence_id"
                                if call["name"] == ToolName.READ_EVIDENCE.value
                                else "url",
                                "",
                            )
                        )[:2000],
                        code=observation.error.code,
                    )
                )
        elif observation.result and observation.result.ok:
            consecutive = 0
        if observation.result:
            evidence.extend(observation.result.evidence_ids)
            if call["name"] == ToolName.READ_EVIDENCE.value and observation.result.ok:
                # Existing source used by this branch, not a new ingestion/page.
                evidence.append(call["args"]["evidence_id"])
                actual_preview = json.loads(observation.message.content)["preview"]
                actual_preview, references, note_issues = number_read_preview(
                    actual_preview, references
                )
                finding_diagnostics.extend(note_issues)
                payload = json.loads(observation.message.content)
                payload["preview"] = actual_preview
                observation.message = observation.message.model_copy(
                    update={
                        "content": json.dumps(
                            payload, ensure_ascii=False, separators=(",", ":")
                        ),
                    }
                )
                observed, diagnostics = capture_read_anchors(
                    actual_preview, call["args"]["evidence_id"]
                )
                combined = merge_read_anchors(anchors, observed)
                if any(anchor not in combined for anchor in observed):
                    diagnostics.append("read_anchor_capacity")
                anchors = combined
                read_diagnostics.extend(diagnostics)
            if call["name"] == ToolName.FETCH_PAGE.value:
                url = call.get("args", {}).get("url")
                if isinstance(url, str) and url.strip() and len(url.strip()) <= 2048:
                    attempted.append(url.strip())
        try:
            await context.event_sink.emit(
                "agent.tool_observation",
                {
                    "run_id": task.run_id,
                    "caller_id": task.caller_id,
                    "branch": task.query,
                    "tool_call_id": call["id"],
                    "tool": call["name"],
                    "result": json.loads(observation.message.content),
                    "research_findings": [
                        f.model_dump(mode="json")
                        for f in observation.research_findings or []
                    ],
                },
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "Agent observation telemetry unavailable", exc_info=True
            )
    completion_summary = next(
        (
            o.completion_summary
            for o in observations.values()
            if o.completion_summary is not None
        ),
        None,
    )
    updates = {
        "messages": [observations[i].message for i in range(len(calls))],
        "todos": todos,
        "evidence_ids": evidence,
        "read_anchors": anchors,
        "read_anchor_diagnostics": list(dict.fromkeys(read_diagnostics))[:100],
        "research_refs": references,
        "research_findings": recorded,
        "research_finding_diagnostics": list(dict.fromkeys(finding_diagnostics))[:100],
        "attempted_urls": attempted,
        "errors": errors,
        "failures": failures[-100:],
        "seen_urls": seen,
        "executed_steps": len(calls),
        "pages_fetched": pages,
        "consecutive_errors": consecutive,
        "stop_reason": stopped,
    }
    if completion_summary is not None and not stopped:
        updates.update(stop_reason="completed", completion_summary=completion_summary)
    return updates
