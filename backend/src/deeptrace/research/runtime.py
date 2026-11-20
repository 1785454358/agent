"""A bounded shared collector: plan, collect, hand actual reads to writing."""

import asyncio
import json
import logging

from langgraph.errors import NodeCancelledError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Overwrite, Send

from deeptrace.domain import (
    ResearchMode,
    ResearchOutcome,
    ResearchRequirement,
    ResearchTopicInput,
    ResearchTopicOutcome,
    TopicStepError,
)
from deeptrace.harness.checkpoint import subgraph_config
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.model_budget import BudgetStateUnavailable
from deeptrace.observability.progress import emit_progress
from deeptrace.research.coverage_review import review_initial_coverage
from deeptrace.research.execution import caller_for_mode
from deeptrace.research.state import ControllerState
from deeptrace.strategies.common import (
    research_input_from_state,
    validated_branch_context,
)
from deeptrace.strategies.model_io import (
    assigned_targets,
    parse_json_object,
    payload_text,
    research_messages,
)
from deeptrace.strategies.planning import parse_research_brief

DEFAULT_MAX_TASKS = 6
DEFAULT_MAX_PARALLEL = 4
DEFAULT_MAX_ROUNDS = 1  # Direct callers opt into the single recovery round.


def _collection_plan(question, payload, limit):
    """Planning labels guide collection; malformed labels cannot veto discovery."""
    payload = payload if isinstance(payload, dict) else {}
    requirements = []
    declared = {}
    for row in (
        payload.get("requirements", [])
        if isinstance(payload.get("requirements"), list)
        else []
    ):
        if (not isinstance(row, dict) or not isinstance(row.get("description"), str)
                or row.get("kind", "fact") != "fact"):
            continue
        text = row["description"].strip()
        if text and len(requirements) < 6:
            identity = f"r{len(requirements) + 1}"
            requirements.append(
                ResearchRequirement(id=identity, description=text[:500])
            )
            if isinstance(row.get("id"), str):
                declared[row["id"]] = identity
    if not requirements:
        requirements = [ResearchRequirement(id="r1", description=question[:500])]
    rows = payload.get("tasks", payload.get("queries", payload.get("assignments", [])))
    briefs, targets = {}, {}
    for row in rows if isinstance(rows, list) else []:
        query = row.get("query") if isinstance(row, dict) else row
        if not isinstance(query, str) or not query.strip() or len(query.strip()) > 1000:
            continue
        query = query.strip()
        if query in targets or len(targets) >= limit:
            continue
        task_briefs = payload.get("task_briefs")
        metadata = (
            row
            if isinstance(row, dict)
            else (task_briefs.get(query, {}) if isinstance(task_briefs, dict) else {})
        )
        metadata = metadata if isinstance(metadata, dict) else {}
        query_targets = payload.get("query_targets")
        ids = metadata.get(
            "requirement_ids",
            query_targets.get(query, []) if isinstance(query_targets, dict) else [],
        )
        targets[query] = (
            list(
                dict.fromkeys(
                    declared[i] for i in ids if isinstance(i, str) and i in declared
                )
            )
            if isinstance(ids, list)
            else []
        )
        targets[query] = targets[query] or [r.id for r in requirements]
        terms = metadata.get("read_terms")
        terms = (
            [
                t.strip()
                for t in terms
                if isinstance(t, str) and 0 < len(t.strip()) <= 600
            ][:6]
            if isinstance(terms, list)
            else []
        )
        seeds = metadata.get("search_queries")
        seeds = (
            [
                s.strip()
                for s in seeds
                if isinstance(s, str) and 0 < len(s.strip()) <= 300
            ][:2]
            if isinstance(seeds, list)
            else []
        )
        briefs[query] = {
            "read_terms": terms or [query[:600]],
            "search_queries": list(dict.fromkeys(seeds)),
        }
    if not targets:
        query = question[:1000]
        targets[query] = [r.id for r in requirements]
        briefs[query] = {"read_terms": [query[:600]]}
    assigned = {identity for ids in targets.values() for identity in ids}
    for requirement in requirements:
        if requirement.id in assigned:
            continue
        query = requirement.description
        matching = next((q for q in targets if q.casefold() == query.casefold()), None)
        if matching is not None:
            targets[matching].append(requirement.id)
        elif len(targets) < limit:
            targets[query] = [requirement.id]
            briefs[query] = {"read_terms": [query]}
    return list(targets), {
        "requirements": requirements,
        "query_targets": targets,
        "research_brief": parse_research_brief(payload),
        "task_briefs": briefs,
        "decomposition_degraded": not bool(payload.get("requirements")),
    }


def build_controller_research_graph(
    topic_graph,
    *,
    mode=ResearchMode.WORKFLOW,
    max_tasks=DEFAULT_MAX_TASKS,
    max_parallel=DEFAULT_MAX_PARALLEL,
    max_rounds=DEFAULT_MAX_ROUNDS,
    checkpointer=None,
):
    if (
        not 1 <= max_tasks <= 6
        or not 1 <= max_parallel <= 16
        or not 1 <= max_rounds <= 3
    ):
        raise ValueError("invalid controller task, parallel or round limit")
    mode = ResearchMode(mode)

    async def plan(state, runtime):
        request = research_input_from_state(state)
        await emit_progress(
            runtime.context, "planning.started", mode=mode.value, round=1
        )
        payload = None
        prompt = (
            f"把原问题拆成可核验的必答事实，规划最多{max_tasks}条互补的首轮查询。"
            "逐一保留对象、对照范围、时间、版本及来源限制。格式、建议和额外背景不列为事实需求。"
            "简单问题用一条直接查询。复杂问题把查询名额分给不同证据路径，避免只改语序或换同义词。"
            "需要数字或趋势时，设计能定位原始统计表、行业协会报告、监管披露或研究方法页的查询，"
            "覆盖历史基数和预测区间；涉及多个地区或对象时，至少尝试一条可找到同口径材料的查询。"
            "术语在公开资料中可能不同，用资料原文常用的统计分类或专业同义词作为查找线索，"
            "保留原问题口径，别假定相邻分类等价。按当前日期理解相对年份，避免无依据地限定单一年份。"
            "选型或技术调研优先定位各方能支撑关键差异、适用条件或故障边界的官方文档、规范或原始报告。"
            "query用短搜索词和可能的资料类型，read_terms用原文可能出现的标题、指标、表头或API名称。"
            '只输出JSON：{"requirements":[{"id":"r1","description":"待调查要点"}],'
            '"tasks":[{"id":"t1","query":"短查询","requirement_ids":["r1"],'
            '"read_terms":["原文定位词"]}]}。最多6个需求；任务至少覆盖所有调查要点。'
        )
        try:
            response = await runtime.context.model_gateway.invoke(
                role="supervisor" if mode is ResearchMode.MULTI_AGENT else "planner",
                messages=research_messages(request, prompt),
            )
            payload = parse_json_object(payload_text(response))
        except (BudgetStateUnavailable, PermissionError, NodeCancelledError):
            raise
        except Exception:
            logging.getLogger(__name__).warning(
                "Planning unavailable; collecting original question", exc_info=True
            )
        queries, contract = _collection_plan(request.question, payload, max_tasks)
        await emit_progress(
            runtime.context,
            "planning.completed",
            mode=mode.value,
            round=1,
            tasks_json=json.dumps(queries, ensure_ascii=False),
        )
        return {
            "delivery_first": True,
            "queries": queries,
            **{
                k: contract.get(k)
                for k in (
                    "requirements",
                    "query_targets",
                    "research_brief",
                    "task_briefs",
                    "decomposition_degraded",
                )
            },
            "topic_outcomes": Overwrite([]),
            "evidence_ids": Overwrite([]),
            "outcome": None,
            "coverage_review": None,
            "first_round_missing": [],
            "supplement_targets": {},
            "supplement_gaps": {},
            "executed_steps": Overwrite(1),
        }

    def dispatch(state, runtime):
        if not state.get("delivery_first"):
            raise ValueError("legacy_research_checkpoint_requires_original_runtime")
        done = {o.query for o in state.get("topic_outcomes") or []}
        remaining = [q for q in state["queries"] if q not in done]
        if getattr(
            runtime.context.model_gateway, "research_exhausted", False
        ) or getattr(runtime.context.model_gateway, "unavailable_reason", None):
            remaining = []
        width = max_parallel if mode is ResearchMode.MULTI_AGENT else 1
        return {"active_queries": remaining[:width]}

    def route(state):
        return [
            Send("execute_task", {**state, "active_query": q})
            for q in state["active_queries"]
        ] or (
            "review_coverage"
            if max_rounds > 1 and state.get("coverage_review", "legacy_checkpoint") is None
            else "finalize"
        )

    async def review_coverage(state, runtime):
        review = await review_initial_coverage(state, runtime.context)
        tasks = list(review.get("supplement_targets", {}))
        await emit_progress(
            runtime.context, "research.coverage.reviewed",
            status=review["coverage_review"],
            missing_requirement_ids=review.get("first_round_missing", []),
            supplement_queries=tasks,
        )
        return {**review, "queries": [*state["queries"], *tasks], "executed_steps": 1}

    async def collect(state, runtime, config):
        query = state["active_query"]
        previous = (
            (state.get("evidence_ids") or [])
            if mode is ResearchMode.PLAN_EXECUTE
            else []
        )
        branch = {
            **state,
            "query": query,
            "evidence_contract_version": 3,
            "target_requirement_ids": assigned_targets(state, query),
            "prior_evidence_ids": list(
                dict.fromkeys([*(state.get("prior_evidence_ids") or []), *previous])
            ),
            "evidence_ids": previous,
        }
        supplement = (state.get("supplement_gaps") or {}).get(query, [])
        if supplement:
            branch["research_gaps"] = supplement
        round_number = 2 if supplement else 1
        await emit_progress(runtime.context, "task.started", task=query, round=round_number)
        try:
            request = ResearchTopicInput(
                run_id=state["run_id"],
                thread_id=state["thread_id"],
                query=query,
                mode=mode,
                caller_id=caller_for_mode(mode),
                **await validated_branch_context(branch, runtime.context),
            )
            raw = await topic_graph.ainvoke(
                {"topic_input": request},
                config=subgraph_config(config),
                context=runtime.context,
            )
            outcome = ResearchTopicOutcome.model_validate(raw["outcome"])
            if outcome.query != query:
                raise ValueError("branch_returned_different_query")
            if outcome.agent_outcome and outcome.agent_outcome.status == "cancelled":
                raise asyncio.CancelledError()
            if any(
                e.code
                in {"tool_not_allowed", "evidence_not_authorized", "url_not_authorized"}
                for e in outcome.errors
            ):
                raise PermissionError("research_source_not_authorized")
        except (BudgetStateUnavailable, PermissionError, NodeCancelledError):
            raise
        except Exception as exc:  # noqa: BLE001 - isolate failed acquisition branches
            outcome = ResearchTopicOutcome(
                query=query,
                errors=[
                    TopicStepError(stage="read", target=query, code=type(exc).__name__)
                ],
                executed_steps=1,
            )
        await emit_progress(
            runtime.context,
            "task.completed",
            task=query,
            round=round_number,
            reason="collected" if outcome.evidence_ids else "source_unavailable",
        )
        return {
            "topic_outcomes": [outcome],
            "evidence_ids": outcome.evidence_ids,
            "executed_steps": outcome.executed_steps,
        }

    def finalize(state, runtime):
        outcomes = state.get("topic_outcomes") or []
        anchors = {a.range_key: a for o in outcomes for a in o.read_anchors}
        limits = [
            f"{o.query}: 本分支未取得完整阅读材料。"
            for o in outcomes
            if o.errors or not o.read_anchors
        ]
        done = {o.query for o in outcomes}
        limits.extend(
            f"{q}: 研究预算到限，尚未收集。" for q in state["queries"] if q not in done
        )
        reason = (
            "model_error"
            if getattr(runtime.context.model_gateway, "unavailable_reason", None)
            else "completed"
            if anchors
            else "no_sources"
        )
        return {
            "outcome": ResearchOutcome(
                delivery_first=True,
                mode=mode,
                evidence_contract_version=3,
                requirements=state.get("requirements") or [],
                decomposition_degraded=state.get("decomposition_degraded", False),
                evidence_ids=list(dict.fromkeys(state.get("evidence_ids") or [])),
                read_anchors=list(anchors.values()),
                findings=[f for o in outcomes for f in o.research_findings],
                unresolved_gaps=limits,
                executed_steps=state.get("executed_steps", 0),
                termination_reason=reason,
            )
        }

    builder = StateGraph(ControllerState, context_schema=HarnessContext)
    for name, node in {
        "plan": plan,
        "dispatch": dispatch,
        "execute_task": collect,
        "review_coverage": review_coverage,
        "finalize": finalize,
    }.items():
        builder.add_node(name, node, input_schema=ControllerState)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "dispatch")
    builder.add_conditional_edges("dispatch", route)
    builder.add_edge("execute_task", "dispatch")
    builder.add_edge("review_coverage", "dispatch")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


async def run_controller_research(
    *,
    research_input,
    context,
    topic_graph,
    max_tasks=DEFAULT_MAX_TASKS,
    max_parallel=DEFAULT_MAX_PARALLEL,
    max_rounds=DEFAULT_MAX_ROUNDS,
    mode=ResearchMode.WORKFLOW,
    config=None,
):
    graph = build_controller_research_graph(
        topic_graph,
        mode=mode,
        max_tasks=max_tasks,
        max_parallel=max_parallel,
        max_rounds=max_rounds,
    )
    result = await graph.ainvoke(
        research_input.model_dump(), config=config, context=context
    )
    return result["outcome"], None
