"""Host-directed acquisition through the existing authenticated tool boundary."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from itertools import zip_longest
from typing import Any
from urllib.parse import urlsplit

from langchain_core.messages import AIMessage

from deeptrace.domain import EvidenceLifecycleStatus
from deeptrace.harness.agent_state import (
    AgentExecutorState,
    AgentTodo,
    TodoStatus,
    topic_input,
)
from deeptrace.harness.agent_tools import execute_batch
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.research_reading import scientific_reading_query
from deeptrace.tools.scraper.research_links import acquisition_links


def reading_query(query: str, original_task: str) -> str:
    """Retain interaction conditions when the user combines capabilities."""
    if re.search(r'\b(combine|together|simultaneous|reconcile|compare|contrast)\b|组合|结合|同时|比较|对比', original_task, re.I):
        suffix = (' 组合使用 兼容 条件 限制' if re.search(r'[\u4e00-\u9fff]', query)
                  else ' compatibility simultaneous support requirements')
        # Retrieval is case-insensitive. Avoid making one CamelCase API name
        # anchor every window when the user asks about cross-feature conditions.
        return query[:1000-len(suffix)].casefold() + suffix
    if re.search(r'\b(version|boundary|prerequisites|limitations)\b|版本|边界|前提|限制', original_task, re.I):
        return query.casefold()
    return query


def _document_version(question):
    match = re.search(r'(?:仅依据|只依据|基于|依据|根据|按照|using|based on|according to).{0,64}?'
                      r'(\d{1,3}\.\d{1,3}(?:\.\d{1,3})?).{0,40}?(?:文档|documentation|docs)',
                      question,re.I)
    return match.group(1) if match else None


def _version_hint(messages, version):
    """Suggest a search path from an observed URL; never authorize a guessed fetch."""
    urls = []
    for message in messages:
        if message.type != 'tool':
            continue
        payload=json.loads(message.content)
        if not payload.get('ok'):
            continue
        for row in json.loads(payload['preview']).get('results',[]):
            urls.append(urlsplit(row.get('url', '')))
    observed = {(url.netloc, url.path) for url in urls}
    for url in urls:
        parts = url.path.split('/')
        for i, part in enumerate(parts):
            if (re.fullmatch(r'v?\d+(?:\.\d+)*', part)
                    and part.lstrip('v').split('.')[0] == version.split('.')[0]):
                parts[i] = ('v' if part.startswith('v') else '') + version
                target_path = '/'.join(parts)
                # A matching exception/reference page does not supply every
                # other page. Skip recovery only for this exact observed path.
                if (url.netloc, target_path) not in observed:
                    return url.netloc + target_path
    return None


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
        result[key] = list(
            dict.fromkeys([*(state.get(key) or []), *(updates.get(key) or [])])
        )
    result["executed_steps"] = state.get("executed_steps", 0) + updates.get(
        "executed_steps", 0
    )
    return result


def node_delta(original, current):
    result = dict(current)
    for key in ("messages", "errors"):
        result[key] = (current.get(key) or [])[len(original.get(key) or []) :]
    for key in ("evidence_ids", "attempted_urls"):
        result[key] = [
            v for v in current.get(key) or [] if v not in (original.get(key) or [])
        ]
    result["executed_steps"] = current.get("executed_steps", 0) - original.get(
        "executed_steps", 0
    )
    for key in ("topic_input", "outcome"):
        result.pop(key, None)
    return result


async def host_tools(
    state: AgentExecutorState,
    context: HarnessContext,
    calls: list[tuple[str, dict[str, Any]]],
    *,
    concurrency: int = 4,
):
    identity = len(state.get("messages") or [])
    requests = []
    for i, (name, args) in enumerate(calls):
        key = f"{identity}:{i}:{name}:{json.dumps(args, sort_keys=True)}"
        requests.append(
            {
                "name": name,
                "args": args,
                "id": "batch-" + hashlib.sha256(key.encode()).hexdigest()[:32],
            }
        )
    dispatch = AIMessage(content="", tool_calls=requests)
    updated = await execute_batch(
        {**state, "messages": [*(state.get("messages") or []), dispatch]},
        context,
        max_concurrency=concurrency,
    )
    return {**updated, "messages": [dispatch, *updated["messages"]]}


async def search_sources(state: AgentExecutorState, context: HarnessContext):
    task = topic_input(state)
    if getattr(context.model_gateway, "unavailable_reason", None) == "model_quota_exhausted":
        return {"stop_reason": "model_error", "todos": stage_todos(0),
                "research_finding_diagnostics": ["model_quota_exhausted"]}
    if getattr(context.model_gateway, "research_exhausted", False):
        return {"stop_reason": "budget_exhausted", "todos": stage_todos(0)}
    if context.source_evidence_ids is not None:
        rows = []
        for identity in context.source_evidence_ids:
            record = await context.evidence_store.get(context.workspace_id, identity)
            if record.status is not EvidenceLifecycleStatus.ACTIVE:
                continue
            rows.append({"id": f"c{len(rows) + 1}", "url": record.canonical_url,
                         "title": record.title, "snippet": "User-provided frozen source; read original evidence before making claims."})
        return {"candidate_urls": [row["url"] for row in rows],
                "source_candidates": rows, "todos": stage_todos(1)}
    seeds = task.search_queries or [task.query]
    version = _document_version(task.original_task)
    calls = [("search_web", {"query": query, "limit": 8})
             for query in list(dict.fromkeys(seeds))[:2]]
    if task.source_policy == "research_results":
        calls = [("search_web", {"query": seeds[-1], "limit": 8})]
        # One complementary discovery pass, parallel and still subject to the
        # shared gateway budget. Preserve base results for recall.
        refined = seeds[0] if task.search_queries else (
            task.query[:900] + " original research paper -conference -workshop -review"
        )
        options = {"query": refined, "limit": 8, "search_depth": "advanced"}
        if task.publication_years:
            first = date(min(task.publication_years), 1, 1)
            last = min(
                date(max(task.publication_years), 12, 31), context.clock.now().date()
            )
            if first > last:
                return {
                    "candidate_urls": [],
                    "source_candidates": [],
                    "todos": stage_todos(1)[:1],
                }
            options.update(start_date=first.isoformat(), end_date=last.isoformat())
        if task.search_queries and len(seeds) == 1:
            calls = [("search_web", options)]
        else:
            calls.insert(0, ("search_web", options))
    if task.source_domains:
        sites = " OR ".join(f"site:{domain}" + (f'/{version}' if version else '') for domain in task.source_domains)
        if len(task.source_domains) > 1:
            sites = f"({sites})"
        # Planner domains are discovery hints, not a complete or verified list
        # of official hosts. Keep primary discovery open for migrated docs;
        # use the other slot for the hint, never expand beyond two searches.
        name, args = calls[-1]
        hinted = (name, {**args, "query": sites + " " + args["query"]})
        if len(calls) == 1:
            calls.append(hinted)
        else:
            calls[-1] = hinted
    if version and not task.source_domains:
        first = await host_tools(state, context, calls[:1])
        hint = _version_hint(first['messages'],version)
        follow = (('search_web',{'query':'site:'+hint+' '+seeds[0],'limit':8})
                  if hint else calls[1] if len(calls)>1 else None)
        if follow:
            current=merge_updates(state,first)
            second=await host_tools(current,context,[follow])
            updated=node_delta(state,merge_updates(current,second))
        else:
            updated=first
    else:
        updated = await host_tools(state, context, calls)
    candidates, rows = [], []
    result_groups = []
    for message in updated["messages"]:
        if message.type != "tool":
            continue
        payload = json.loads(message.content)
        if payload.get("ok"):
            result_groups.append(json.loads(payload["preview"]).get("results", []))
    for rank in zip_longest(*result_groups):
        for row in rank:
            if row:
                url = row.get("url")
                if isinstance(url, str) and url not in candidates:
                    candidates.append(url)
                    rows.append(
                        {
                            "id": f"c{len(candidates)}",
                            "url": url[:2048],
                            "title": str(row.get("title") or "")[:300],
                            "snippet": str(row.get("snippet") or "")[:1000],
                            "discovery_date": row.get("discovery_date"),
                        }
                    )
    cap = 12 if task.source_policy == "research_results" else 8
    from deeptrace.harness.source_navigation import source_link_candidates

    navigation = await source_link_candidates(task, context)
    if navigation:
        # Search and actually observed links share the same selection, fetch,
        # page budget and read pipeline. No fabricated URL or new LLM call.
        urls = {row["url"] for row in navigation}
        rows = [*navigation, *(row for row in rows if row["url"] not in urls)]
        for index, row in enumerate(rows, 1):
            row["id"] = f"c{index}"
        candidates = [row["url"] for row in rows]
        updated["seen_urls"] = list(dict.fromkeys([
            *(updated.get("seen_urls") or state.get("seen_urls") or []),
            *(row["url"] for row in navigation),
        ]))
    if version:
        # Merge and rank before the cap: otherwise broad latest-version hits
        # can evict the targeted pass before source selection ever sees it.
        rows.sort(key=lambda row: not any(
            part in {version, 'v' + version}
            for part in urlsplit(row['url']).path.split('/')))
        candidates = [row['url'] for row in rows]
    return {
        **updated,
        "candidate_urls": candidates[:cap],
        "source_candidates": rows[:cap],
        "todos": stage_todos(1) if candidates else stage_todos(1)[:1],
    }


async def fetch_sources(
    state: AgentExecutorState,
    context: HarnessContext,
    *,
    source_target: int = 3,
    concurrency: int = 4,
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
    candidates = [url for url in state.get("candidate_urls") or [] if url not in task.blocked_acquisitions]
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
        if (task.source_policy != "research_results" and context.source_evidence_ids is None
                and not current.get("stop_reason")):
            from deeptrace.harness.source_navigation import reference_index_links

            calls = []
            remaining = max(0, task.max_pages - current.get("pages_fetched", 0))
            for identity in selected:
                record = await context.evidence_store.get(context.workspace_id, identity)
                body = await context.evidence_store.read_body(context.workspace_id, identity)
                for url in reference_index_links(task, record, body, current.get("seen_urls") or []):
                    if url not in (current.get("attempted_urls") or []) and ("fetch_page", {"url": url}) not in calls:
                        calls.append(("fetch_page", {"url": url}))
            if calls and remaining:
                updated = await host_tools(current, context, calls[:min(2, remaining)], concurrency=concurrency)
                current = merge_updates(current, updated)
                selected = list(dict.fromkeys([*(updated.get("evidence_ids") or []), *selected]))[:target]
        if task.source_policy == "research_results" and not current.get("stop_reason"):
            # Follow one explicit original-paper anchor per secondary page.
            # Gateway authorization comes from the actually fetched page body.
            primary_calls = []
            primary_origins = {}
            seen_links = set()
            remaining = max(0, task.max_pages - current.get("pages_fetched", 0))
            for identity in selected:
                record = await context.evidence_store.get(context.workspace_id, identity)
                body = await context.evidence_store.read_body(context.workspace_id, identity)
                links = [u for u in acquisition_links(record.canonical_url, body)
                         if u in (current.get("seen_urls") or [])
                         and u not in seen_links
                         and u not in (current.get("attempted_urls") or [])]
                if links and len(primary_calls) < min(target, remaining):
                    primary_calls.append(("fetch_page", {"url": links[0]}))
                    primary_origins[links[0]] = identity
                    seen_links.add(links[0])
            if primary_calls:
                updated = await host_tools(current, context, primary_calls, concurrency=concurrency)
                current = merge_updates(current, updated)
                originals = list(dict.fromkeys(updated.get("evidence_ids") or []))
                if originals:
                    resolved = set()
                    for identity in originals:
                        record = await context.evidence_store.get(context.workspace_id, identity)
                        origin = primary_origins.get(record.metadata.get("requested_url") or record.canonical_url)
                        if origin is not None:
                            resolved.add(origin)
                    selected = list(dict.fromkeys([*originals,
                        *(identity for identity in selected if identity not in resolved)]))[:target]
        todos = stage_todos(2)
    else:
        attempted_stages = 2 if state.get("candidate_urls") else 1
        todos = stage_todos(2)[:attempted_stages]
    return {
        **node_delta(state, current),
        "batch_selected_ids": selected,
        "todos": todos,
    }


async def read_sources(
    state: AgentExecutorState,
    context: HarnessContext,
    *,
    concurrency: int = 4,
):
    task = topic_input(state)
    identities = state.get("batch_selected_ids") or []
    if not identities or state.get("stop_reason"):
        return {}
    calls = []
    reading = state.get("batch_read_queries") or {}
    assigned = [r for r in task.requirements
                if not task.target_requirement_ids or r.id in task.target_requirement_ids]
    queries = []
    for requirement in assigned:
        # Reused sources bypass discovery; retain the branch's locator terms.
        hints = reading.get(requirement.id) or task.read_terms or requirement.description
        # Old checkpoints stored a single string per requirement.
        for query in hints if isinstance(hints, list) else [hints]:
            if query not in queries:
                queries.append(query)
    queries = queries or [task.query]
    for identity in identities:
        if task.source_policy == "research_results":
            # Keep publication/abstract context and read the assigned research
            # dimensions, not just a topic-level 1000-character hit.
            calls.extend(
                [
                    (
                        "read_evidence",
                        {"evidence_id": identity, "start": 0, "limit": 2000},
                    ),
                ]
            )
            calls.extend(("read_evidence", {"evidence_id": identity, "query": scientific_reading_query(query), "limit": 3000})
                         for query in queries[:6])
        else:
            for query in list(dict.fromkeys(queries or [task.query]))[:6]:
                calls.append(("read_evidence", {
                    "evidence_id": identity, "query": reading_query(query, task.original_task), "limit": 3000,
                }))
    updated = await host_tools(
        state,
        context,
        calls,
        concurrency=concurrency,
    )
    previews = []
    for message in updated["messages"]:
        if message.type == "tool":
            payload = json.loads(message.content)
            if payload.get("ok"):
                preview = json.loads(payload["preview"])
                if preview.get("passages"):
                    record = await context.evidence_store.get(
                        context.workspace_id, preview["evidence_id"]
                    )
                    preview.update(
                        url=record.canonical_url,
                        title=record.title,
                        published_at=record.published_at.isoformat()
                        if record.published_at
                        else None,
                    )
                    previews.append(preview)
    # Todos track host steps; actual tool observations retain failed reads.
    return {**updated, "batch_read_previews": previews, "todos": stage_todos(3)}
