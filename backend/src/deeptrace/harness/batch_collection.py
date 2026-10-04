"""Host-directed acquisition through the existing authenticated tool boundary."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from langchain_core.messages import AIMessage

from deeptrace.domain import EvidenceLifecycleStatus
from deeptrace.harness.agent_state import AgentExecutorState, AgentTodo, TodoStatus, topic_input
from deeptrace.harness.agent_tools import execute_batch
from deeptrace.harness.context import HarnessContext


def stage_todos(completed: int) -> list[AgentTodo]:
    return [
        AgentTodo(
            content=label,
            status=TodoStatus.COMPLETED if i < completed else TodoStatus.PENDING,
        )
        for i, label in enumerate(("检索资料", "抓取原文", "读取证据"))
    ]


def merge_updates(state, updates):
    """Match AgentExecutorState reducers when several host waves share a node."""
    result = {**state, **updates}
    for key in ("messages", "errors"):
        result[key] = [*(state.get(key) or []), *(updates.get(key) or [])]
    for key in ("evidence_ids", "attempted_urls"):
        result[key] = list(dict.fromkeys([*(state.get(key) or []), *(updates.get(key) or [])]))
    result["executed_steps"] = state.get("executed_steps", 0) + updates.get("executed_steps", 0)
    return result


def node_delta(original, current):
    result = dict(current)
    for key in ("messages", "errors"):
        result[key] = (current.get(key) or [])[len(original.get(key) or []):]
    for key in ("evidence_ids", "attempted_urls"):
        result[key] = [v for v in current.get(key) or [] if v not in (original.get(key) or [])]
    result["executed_steps"] = current.get("executed_steps", 0) - original.get("executed_steps", 0)
    for key in ("topic_input", "outcome"):
        result.pop(key, None)
    return result


async def host_tools(
    state: AgentExecutorState, context: HarnessContext,
    calls: list[tuple[str, dict[str, Any]]], *, concurrency: int = 4,
):
    identity = len(state.get("messages") or [])
    requests = []
    for i, (name, args) in enumerate(calls):
        key = f"{identity}:{i}:{name}:{json.dumps(args, sort_keys=True)}"
        requests.append({
            "name": name, "args": args,
            "id": "batch-" + hashlib.sha256(key.encode()).hexdigest()[:32],
        })
    dispatch = AIMessage(content="", tool_calls=requests)
    updated = await execute_batch(
        {**state, "messages": [*(state.get("messages") or []), dispatch]},
        context, max_concurrency=concurrency,
    )
    return {**updated, "messages": [dispatch, *updated["messages"]]}


async def search_sources(state: AgentExecutorState, context: HarnessContext):
    task = topic_input(state)
    if getattr(context.model_gateway, "research_exhausted", False):
        return {"stop_reason": "budget_exhausted", "todos": stage_todos(0)}
    updated = await host_tools(
        state, context, [("search_web", {"query": task.query, "limit": 8})],
    )
    candidates = []
    for message in updated["messages"]:
        if message.type != "tool":
            continue
        payload = json.loads(message.content)
        if payload.get("ok"):
            for row in json.loads(payload["preview"]).get("results", []):
                url = row.get("url")
                if isinstance(url, str) and url not in candidates:
                    candidates.append(url)
    return {**updated, "candidate_urls": candidates[:8],
            "todos": stage_todos(1) if candidates else stage_todos(1)[:1]}


async def fetch_sources(
    state: AgentExecutorState, context: HarnessContext,
    *, source_target: int = 3, concurrency: int = 4,
):
    task = topic_input(state)
    target = min(source_target, task.max_pages)
    known = {}
    for identity in task.authorized_evidence_ids:
        try:
            record = await context.evidence_store.get(context.workspace_id, identity)
        except KeyError:
            continue
        if record.status is EvidenceLifecycleStatus.ACTIVE:
            known[record.canonical_url] = record.id
    current = dict(state)
    selected = []
    candidates = list(state.get("candidate_urls") or [])
    while candidates and len(selected) < target and not current.get("stop_reason"):
        if getattr(context.model_gateway, "research_exhausted", False):
            current["stop_reason"] = "budget_exhausted"
            break
        wave = []
        while candidates and len(selected) + len(wave) < target:
            url = candidates.pop(0)
            if url in known:
                if known[url] not in selected:
                    selected.append(known[url])
            elif url not in (current.get("attempted_urls") or []):
                wave.append(("fetch_page", {"url": url}))
        if wave:
            updated = await host_tools(current, context, wave, concurrency=concurrency)
            current = merge_updates(current, updated)
            for identity in updated["evidence_ids"]:
                if identity not in selected:
                    selected.append(identity)
    if selected:
        todos = stage_todos(2)
    else:
        attempted_stages = 2 if state.get("candidate_urls") else 1
        todos = stage_todos(2)[:attempted_stages]
    return {**node_delta(state, current), "batch_selected_ids": selected, "todos": todos}


async def read_sources(
    state: AgentExecutorState, context: HarnessContext, *, concurrency: int = 4,
):
    task = topic_input(state)
    identities = state.get("batch_selected_ids") or []
    if not identities or state.get("stop_reason"):
        return {}
    updated = await host_tools(
        state, context,
        [("read_evidence", {"evidence_id": identity, "query": task.query})
         for identity in identities],
        concurrency=concurrency,
    )
    previews = []
    for message in updated["messages"]:
        if message.type == "tool":
            payload = json.loads(message.content)
            if payload.get("ok"):
                preview = json.loads(payload["preview"])
                if preview.get("passages"):
                    record = await context.evidence_store.get(context.workspace_id, preview["evidence_id"])
                    preview.update(url=record.canonical_url, title=record.title,
                                   published_at=record.published_at.isoformat() if record.published_at else None)
                    previews.append(preview)
    # Todos track host steps; actual tool observations retain failed reads.
    return {**updated, "batch_read_previews": previews,
            "todos": stage_todos(3)}
