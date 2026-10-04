"""Run the research-mode matrix over a corpus and collect raw records."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from time import perf_counter
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from deeptrace.application.research import (
    ApplicationResearchRequest,
    ResearchApplicationService,
)
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.eval.baseline import build_baseline_research_graph
from deeptrace.eval.dataset import EvalQuestion
from deeptrace.eval.env import Corpus, EvalFaults, build_eval_context
from deeptrace.eval.experiment import EvaluationLimits
from deeptrace.eval.judge import (
    MAX_ANSWER_CHARS,
    MAX_EVIDENCE_CHARS,
    JudgeScore,
    judge_record,
)
from deeptrace.eval.telemetry import RequestCounter
from deeptrace.harness.agent_executor import build_research_agent_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.registry import (
    ResponseGraphRegistry,
    ResponseRegistration,
    StrategyRegistration,
    StrategyRegistry,
)
from deeptrace.responses import (
    build_answer_graph,
    build_brief_graph,
    build_report_graph,
)
from deeptrace.strategies import (
    build_multi_agent_research_graph,
    build_plan_execute_research_graph,
    build_workflow_research_graph,
)


class RunRecord(BaseModel):
    """One ``(question, mode, repeat)`` execution with the fields scoring needs."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    mode: str
    question: str
    run_id: str
    repeat_index: int = 0
    status: Literal["completed", "partial", "failed"]
    termination_reason: str
    research_termination_reason: str | None = None
    response_partial_reason: str | None = None
    unresolved_gaps: list[str] = Field(default_factory=list)
    answered: bool
    answer: str = ""
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list)
    artifact_errors: list[str] = Field(default_factory=list)
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    executed_steps: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    fetched_pages: int = 0
    tool_retries: int = 0
    wall_ms: float = 0.0
    judge: JudgeScore | None = None
    judge_attempted: bool = False
    judge_error: str | None = None
    system_error: str | None = None
    trajectory: dict[str, JsonValue] = Field(
        default_factory=lambda: {"model_turns": [], "tool_executions": []}
    )


def build_eval_graph(*, max_iterations: int = 8, baseline: bool = False):
    """Compile the top-level runtime with all strategies sharing one loop."""

    executor = build_research_agent_graph(max_iterations=max_iterations)
    strategies = StrategyRegistry()
    for registration in (
        StrategyRegistration(
            ResearchMode.WORKFLOW,
            build_baseline_research_graph()
            if baseline
            else build_workflow_research_graph(executor),
        ),
        StrategyRegistration(
            ResearchMode.PLAN_EXECUTE, build_plan_execute_research_graph(executor)
        ),
        StrategyRegistration(
            ResearchMode.MULTI_AGENT, build_multi_agent_research_graph(executor)
        ),
    ):
        strategies.register(registration)
    responses = ResponseGraphRegistry()
    for mode, builder in (
        (ResponseMode.ANSWER, build_answer_graph),
        (ResponseMode.BRIEF, build_brief_graph),
        (ResponseMode.REPORT, build_report_graph),
    ):
        responses.register(ResponseRegistration(mode, builder()))
    return build_agent_runtime_graph(
        strategies,
        responses,
        checkpointer=InMemorySaver(serde=create_harness_checkpoint_serializer()),
    )


def _run_id(
    prefix: str, question_id: str, mode: ResearchMode, repeat: int, repeats: int
) -> str:
    base = f"{prefix}-{question_id}-{mode}"
    return f"{base}-r{repeat}" if repeats > 1 else base


async def _judge(
    judge_factory: Callable[[], object],
    *,
    question: EvalQuestion,
    answer: str,
    evidence_store,
    workspace_id: str,
    evidence,
) -> tuple[JudgeScore | None, str | None]:
    bodies: list[str] = []
    for record in evidence:
        try:
            body = await evidence_store.read_body(workspace_id, record.id)
        except (KeyError, ValueError):
            body = ""
        bodies.append(f"[{record.id}] {record.title}\n{body[:MAX_EVIDENCE_CHARS]}")
    try:
        score = await judge_record(
            gateway=judge_factory(),
            question=question.question,
            answer=answer[:MAX_ANSWER_CHARS],
            evidence_text="\n\n".join(bodies),
            gold_answer=question.gold_answer,
        )
        return score, None
    except Exception as exc:  # noqa: BLE001 - record judge failures, never zero-impute.
        return None, type(exc).__name__


async def _capture_evidence(env, selected_ids):
    ids = list(selected_ids)
    for row in env.trajectory.snapshot(full=True)["tool_results"]:
        for evidence_id in (row.get("result") or {}).get("evidence_ids", []):
            if evidence_id not in ids:
                ids.append(evidence_id)
    errors = []
    try:
        evidence = await env.evidence_store.get_many(env.context.workspace_id, ids)
    except Exception as exc:  # noqa: BLE001 - flag missing artifacts without rewriting application status.
        return (), [], [type(exc).__name__]
    snapshots = []
    for item in evidence:
        try:
            body = await env.evidence_store.read_body(env.context.workspace_id, item.id)
        except Exception as exc:  # noqa: BLE001 - cancellation still propagates.
            errors.append(type(exc).__name__)
            continue
        snapshots.append(
            {
                "id": item.id,
                "url": item.canonical_url,
                "title": item.title,
                "body": body,
                "selected_for_outcome": item.id in selected_ids,
                "content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        )
    return evidence, snapshots, errors


async def run_matrix(
    questions: list[EvalQuestion],
    corpus: Corpus | None,
    *,
    model_factory: Callable[[], object],
    modes: tuple[ResearchMode, ...] | None = None,
    run_prefix: str = "eval",
    faults: EvalFaults | None = None,
    repeats: int = 1,
    judge_factory: Callable[[], object] | None = None,
    limits: EvaluationLimits | None = None,
    store=None,
    batch_model_counter: RequestCounter | None = None,
    response_mode: ResponseMode | None = None,
    include_baseline: bool = False,
    response_max_content_chars: int | None = None,
    environment_factory=None,
) -> list[RunRecord]:
    """Execute every ``(question, mode, repeat)`` against a fresh context."""

    if not questions:
        raise ValueError("questions must not be empty")
    if corpus is None and environment_factory is None:
        raise ValueError("explicit environment factory required without corpus")
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if response_max_content_chars is not None and (
        type(response_max_content_chars) is not int or response_max_content_chars < 1
    ):
        raise ValueError("response_max_content_chars must be a positive integer")
    selected = modes or tuple(ResearchMode)
    if len(selected) != len(set(selected)):
        raise ValueError("modes must be unique")
    resolved = limits or EvaluationLimits()
    systems = [(mode.value, mode) for mode in selected]
    if include_baseline:
        systems.append(("baseline", ResearchMode.WORKFLOW))
    cached = {}
    for question in questions:
        for label, mode in systems:
            for repeat in range(repeats):
                run_id = _run_id(run_prefix, question.id, label, repeat, repeats)
                if run_id in cached:
                    raise ValueError("run IDs must be unique")
                ApplicationResearchRequest(
                    run_id=run_id,
                    thread_id=run_id,
                    question=question.question,
                    mode=mode,
                    response_mode=response_mode,
                )
                saved = store.load(run_id) if store else None
                cached[run_id] = RunRecord.model_validate(saved) if saved else None
    if batch_model_counter is None and resolved.max_batch_model_calls is not None:
        batch_model_counter = RequestCounter(
            resolved.max_batch_model_calls,
            used=sum(r.model_calls for r in cached.values() if r is not None),
        )
    graph = build_eval_graph(max_iterations=resolved.agent_iterations)
    service = ResearchApplicationService(graph)
    baseline_service = (
        ResearchApplicationService(
            build_eval_graph(max_iterations=resolved.agent_iterations, baseline=True)
        )
        if include_baseline
        else None
    )
    records: list[RunRecord] = []

    for question in questions:
        for label, mode in systems:
            for repeat in range(repeats):
                run_id = _run_id(run_prefix, question.id, label, repeat, repeats)
                if cached[run_id] is not None:
                    records.append(cached[run_id])
                    continue
                if store:
                    store.claim(run_id)
                env = (environment_factory or build_eval_context)(
                    corpus,
                    model_gateway=model_factory(),
                    run_id=run_id,
                    faults=faults,
                    limits=resolved,
                    batch_model_counter=batch_model_counter,
                    memory_enabled=False,
                    response_max_content_chars=response_max_content_chars,
                )
                started = perf_counter()
                try:
                    async with asyncio.timeout(resolved.run_timeout_seconds):
                        selected_service = (
                            baseline_service if label == "baseline" else service
                        )
                        result = await selected_service.invoke(
                            ApplicationResearchRequest(
                                run_id=run_id,
                                thread_id=run_id,
                                question=question.question,
                                mode=mode,
                                response_mode=response_mode,
                            ),
                            config={"configurable": {"thread_id": run_id}},
                            context=env.context,
                        )
                except Exception as exc:  # noqa: BLE001 - record sample failure; cancellation propagates.
                    evidence, snapshots, artifact_errors = await _capture_evidence(
                        env, []
                    )
                    records.append(
                        RunRecord(
                            question_id=question.id,
                            mode=label,
                            question=question.question,
                            run_id=run_id,
                            repeat_index=repeat,
                            status="failed",
                            termination_reason="execution_error",
                            answered=False,
                            system_error=type(exc).__name__,
                            evidence=snapshots,
                            evidence_ids=[item.id for item in evidence],
                            evidence_urls=[item.canonical_url for item in evidence],
                            artifact_errors=artifact_errors,
                            model_calls=env.model_calls,
                            tool_calls=env.tool_calls,
                            fetched_pages=env.fetched_pages,
                            wall_ms=(perf_counter() - started) * 1000,
                            trajectory=env.trajectory.snapshot(full=True),
                            usage=env.usage_snapshot(),
                        )
                    )
                    if store:
                        store.save(records[-1].model_dump(mode="json"))
                    continue
                finally:
                    await env.aclose()
                wall_ms = (perf_counter() - started) * 1000

                research = result.research_outcome
                response = result.response_outcome
                answer = str(response.content)
                evidence, evidence_snapshots, artifact_errors = await _capture_evidence(
                    env, research.evidence_ids if research else []
                )
                judge_score: JudgeScore | None = None
                judge_error = None
                if judge_factory is not None:
                    judge_score, judge_error = await _judge(
                        judge_factory,
                        question=question,
                        answer=answer,
                        evidence_store=env.evidence_store,
                        workspace_id=env.context.workspace_id,
                        evidence=evidence,
                    )
                records.append(
                    RunRecord(
                        question_id=question.id,
                        mode=label,
                        question=question.question,
                        run_id=run_id,
                        repeat_index=repeat,
                        status=result.status,
                        termination_reason=result.termination_reason,
                        research_termination_reason=research.termination_reason
                        if research
                        else None,
                        response_partial_reason=response.partial_reason,
                        unresolved_gaps=list(result.unresolved_gaps),
                        answered=response.partial_reason is None,
                        answer=answer,
                        evidence=evidence_snapshots,
                        artifact_errors=artifact_errors,
                        usage=env.usage_snapshot(),
                        evidence_ids=list(research.evidence_ids) if research else [],
                        evidence_urls=[record.canonical_url for record in evidence],
                        cited_evidence_ids=list(response.cited_evidence_ids),
                        executed_steps=result.executed_steps,
                        model_calls=env.model_calls,
                        tool_calls=env.tool_calls,
                        fetched_pages=env.fetched_pages,
                        tool_retries=sum(
                            1
                            for event_type, _payload in env.events.events
                            if event_type == "tool.retry"
                        ),
                        wall_ms=wall_ms,
                        judge=judge_score,
                        judge_attempted=judge_factory is not None,
                        judge_error=judge_error,
                        trajectory=env.trajectory.snapshot(full=True),
                    )
                )
                if store:
                    store.save(records[-1].model_dump(mode="json"))
    return records
