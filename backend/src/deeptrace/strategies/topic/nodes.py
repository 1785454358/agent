"""Deterministic nodes for the research topic subgraph."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from langgraph.types import Send

from deeptrace.domain import (
    TRANSIENT_TOOL_ERROR_CODES,
    ResearchMode,
    ResearchTopicInput,
    ResearchTopicOutcome,
    ToolName,
    ToolRequest,
    ToolResult,
    TopicStepError,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.tools.policy import CallerRole, ToolCaller, UrlAuthorization, UrlAuthorizationSource
from deeptrace.tools.scraper.urls import normalize_url_before_fetch, validate_public_url

from deeptrace.strategies.topic.state import FetchBranchState, ResearchTopicState


class TransientToolError(RuntimeError):
    """Raised by nodes so LangGraph RetryPolicy can replay the node."""


def _raise_if_transient(result: ToolResult) -> ToolResult:
    if not result.ok and result.error_code in TRANSIENT_TOOL_ERROR_CODES:
        raise TransientToolError(
            f"transient tool failure: {result.error_code}"
        )
    return result


_ROLE_BY_MODE: dict[ResearchMode, CallerRole] = {
    ResearchMode.WORKFLOW: CallerRole.WORKFLOW_GRAPH,
    ResearchMode.PLAN_EXECUTE: CallerRole.PLAN_EXECUTE_EXECUTOR,
    ResearchMode.MULTI_AGENT: CallerRole.MULTI_AGENT_RESEARCHER,
}


def _role_for_mode(mode: ResearchMode) -> CallerRole:
    return _ROLE_BY_MODE[mode]


def _caller(topic_input: ResearchTopicInput) -> ToolCaller:
    return ToolCaller(
        caller_id=topic_input.caller_id,
        role=_role_for_mode(topic_input.mode),
        mode=topic_input.mode,
    )


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _request_id(topic_input: ResearchTopicInput) -> str:
    return "request-" + _digest(
        f"research_topic\0{topic_input.thread_id}\0{topic_input.run_id}\0{topic_input.query}"
    )


def _call_id(topic_input: ResearchTopicInput, stage: str, target: str, ordinal: int) -> str:
    return "call-" + _digest(
        f"{topic_input.run_id}\0{stage}\0{topic_input.query}\0{target}\0{ordinal}"
    )


def _topic_input(state: ResearchTopicState) -> ResearchTopicInput:
    return ResearchTopicInput.model_validate(state["topic_input"])


def _tenant_id(runtime: Runtime[HarnessContext]) -> str:
    return runtime.context.workspace_id


async def search_node(
    state: ResearchTopicState,
    runtime: Runtime[HarnessContext],
) -> dict[str, Any]:
    topic_input = _topic_input(state)
    request = ToolRequest(
        request_id=_request_id(topic_input),
        run_id=topic_input.run_id,
        thread_id=topic_input.thread_id,
        call_id=_call_id(topic_input, "search", "", 0),
        tool=ToolName.SEARCH_WEB,
        arguments={"query": topic_input.query, "limit": topic_input.max_pages},
    )
    result = await runtime.context.tool_gateway.execute(
        tenant_id=_tenant_id(runtime),
        caller=_caller(topic_input),
        request=request,
    )
    _raise_if_transient(result)
    return {"search_result": result, "executed_steps": 1}


def _search_errors(result: ToolResult | None) -> list[TopicStepError]:
    if result is None:
        return [TopicStepError(stage="search", target="", code="search_skipped")]
    if not result.ok:
        assert result.error_code is not None
        return [
            TopicStepError(stage="search", target="", code=result.error_code)
        ]
    return []


def _urls_from_preview(preview: str) -> list[str]:
    try:
        payload = json.loads(preview)
    except (TypeError, ValueError) as exc:
        raise ValueError("search preview is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("search preview must be an object")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("search preview has no results list")
    urls: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        try:
            safe, _reason = validate_public_url(url)
        except (TypeError, ValueError):
            continue
        if not safe:
            continue
        try:
            urls.append(normalize_url_before_fetch(url))
        except (TypeError, ValueError):
            continue
    return urls


def select_urls_node(state: ResearchTopicState) -> dict[str, Any]:
    topic_input = _topic_input(state)
    result = state.get("search_result")
    errors: list[TopicStepError] = []
    selected: list[str] = []
    if result is None or not result.ok:
        errors = _search_errors(result)
    else:
        try:
            candidates = _urls_from_preview(result.preview)
        except ValueError:
            errors = [
                TopicStepError(
                    stage="search", target="", code="malformed_search_preview"
                )
            ]
        else:
            for url in candidates:
                if url not in selected:
                    selected.append(url)
                if len(selected) >= topic_input.max_pages:
                    break
            if not selected:
                errors = [
                    TopicStepError(
                        stage="search", target="", code="no_search_results"
                    )
                ]
    return {"selected_urls": selected, "errors": errors}


def route_fetches(state: ResearchTopicState) -> list[Send] | str:
    topic_input = _topic_input(state)
    selected = state.get("selected_urls") or []
    if not selected:
        return "finalize"
    return [
        Send(
            "fetch_page",
            FetchBranchState(
                run_id=topic_input.run_id,
                thread_id=topic_input.thread_id,
                query=topic_input.query,
                url=url,
                ordinal=ordinal,
                mode=topic_input.mode,
                caller_id=topic_input.caller_id,
            ),
        )
        for ordinal, url in enumerate(selected)
    ]


async def fetch_page_node(
    state: FetchBranchState,
    runtime: Runtime[HarnessContext],
) -> dict[str, Any]:
    topic_input = ResearchTopicInput(
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        query=state["query"],
        mode=state["mode"],
        caller_id=state["caller_id"],
    )
    url = state["url"]
    request = ToolRequest(
        request_id=_request_id(topic_input),
        run_id=topic_input.run_id,
        thread_id=topic_input.thread_id,
        call_id=_call_id(topic_input, "fetch", url, state["ordinal"]),
        tool=ToolName.FETCH_PAGE,
        arguments={"url": url},
    )
    authorization = UrlAuthorization(
        source=UrlAuthorizationSource.SEARCH_RESULT,
        urls=frozenset({url}),
    )
    result = await runtime.context.tool_gateway.execute(
        tenant_id=_tenant_id(runtime),
        caller=_caller(topic_input),
        request=request,
        authorization=authorization,
    )
    _raise_if_transient(result)
    updates: dict[str, Any] = {
        "executed_steps": 1,
        "attempted_urls": [url],
    }
    if result.ok:
        updates["evidence_ids"] = list(result.evidence_ids)
    else:
        assert result.error_code is not None
        updates["errors"] = [
            TopicStepError(stage="fetch", target=url, code=result.error_code)
        ]
    return updates


def finalize_node(state: ResearchTopicState) -> dict[str, Any]:
    topic_input = _topic_input(state)
    evidence_ids = sorted(set(state.get("evidence_ids") or []))
    attempted_urls = sorted(set(state.get("attempted_urls") or []))
    errors = sorted(
        state.get("errors") or [],
        key=lambda error: (error.stage, error.target, error.code),
    )
    outcome = ResearchTopicOutcome(
        query=topic_input.query,
        evidence_ids=evidence_ids,
        attempted_urls=attempted_urls,
        errors=errors,
        executed_steps=state.get("executed_steps") or 0,
    )
    return {"outcome": outcome}
