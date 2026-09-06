"""Supervisor planning and batch review."""

from __future__ import annotations

import asyncio
from datetime import datetime

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from deeptrace.multi_agent.models import (
    SUPERVISOR_TOOL,
    AssignmentDraft,
    SupervisorDecision,
    SupervisorOutcome,
)
from deeptrace.multi_agent.prompts import supervisor_messages


class DecisionError(ValueError):
    """A sanitized Supervisor decision failure safe to expose in events."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _normalized_history(history: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for raw in history:
        item = raw.model_dump() if hasattr(raw, "model_dump") else raw
        if not isinstance(item, dict):
            continue
        if "assignment" not in item:
            normalized.append(item)
            continue
        assignment = item.get("assignment") or {}
        result = item.get("result") or {}
        if not isinstance(assignment, dict) or not isinstance(result, dict):
            continue
        normalized.append(
            {
                "id": assignment.get("id"),
                "objective": assignment.get("objective", ""),
                "required_outputs": assignment.get("required_outputs", []),
                "excluded_scope": assignment.get("excluded_scope", []),
                "source_guidance": assignment.get("source_guidance", []),
                "parent_ids": assignment.get("parent_ids", []),
                "status": result.get("status", "pending"),
                "summary": result.get("summary", ""),
                "gaps": result.get("gaps", []),
                "source_count": len(result.get("source_urls", [])),
            }
        )
    return normalized


def _history_gaps(history: list[dict]) -> list[str]:
    gaps: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        for gap in item.get("gaps", []):
            if isinstance(gap, str) and gap.strip() and gap not in gaps:
                gaps.append(gap)
                if len(gaps) == 6:
                    return gaps
    return gaps


def _bounded_unique(values: list, extra: str) -> list[str]:
    unique = [str(value).strip() for value in values if str(value).strip()]
    unique.append(extra)
    return list(dict.fromkeys(unique))[:6]


def _group_gaps(gaps: list[str], groups: int = 3) -> list[str]:
    clean = list(dict.fromkeys(gap.strip() for gap in gaps if gap.strip()))
    if not clean:
        return []
    buckets: list[list[str]] = [
        [] for _ in range(min(groups, len(clean)))
    ]
    for index, gap in enumerate(clean):
        buckets[index % len(buckets)].append(gap)
    return ["；".join(bucket)[:1000] for bucket in buckets]


def build_gap_followups(
    history: list[dict], *, max_assignments: int
) -> list[AssignmentDraft]:
    """Build one bounded follow-up for each unresolved executed leaf task."""
    normalized = _normalized_history(history)
    superseded = {
        parent_id
        for item in normalized
        if item.get("status") in {"completed", "partial", "blocked"}
        for parent_id in item.get("parent_ids", [])
    }
    followups: list[AssignmentDraft] = []
    for item in normalized:
        task_id = item.get("id")
        gaps = [gap for gap in item.get("gaps", []) if isinstance(gap, str)]
        if (
            not task_id
            or task_id in superseded
            or item.get("status") not in {"partial", "blocked"}
            or not gaps
        ):
            continue
        followups.append(
            AssignmentDraft(
                objective=f"补充并核实 {task_id} 未完成的关键资料",
                required_outputs=_group_gaps(gaps),
                excluded_scope=_bounded_unique(
                    item.get("excluded_scope", []), "不重复已确认内容"
                ),
                source_guidance=_bounded_unique(
                    item.get("source_guidance", []), "优先官方或一手来源"
                ),
                parent_ids=[task_id],
            )
        )
        if len(followups) >= max(0, max_assignments):
            break
    return followups


class Supervisor:
    def __init__(self, model, runtime) -> None:
        self.model = model
        self.runtime = runtime

    def _fallback(
        self,
        history: list[dict],
        *,
        can_dispatch: bool,
        max_assignments: int,
        reason_code: str,
        circuit_open: bool,
    ) -> SupervisorOutcome:
        followups = (
            build_gap_followups(history, max_assignments=max_assignments)
            if can_dispatch
            else []
        )
        self.runtime.emit(
            "supervisor.fallback",
            "主管未返回有效决策，使用确定性计划降级",
            reason_code=reason_code,
            action="dispatch" if followups else "finish",
        )
        if followups:
            decision = SupervisorDecision(
                action="dispatch",
                rationale="主管不可用，按未解决叶子任务生成定向补查",
                assignments=followups,
                sufficient=False,
                gaps=[],
            )
        else:
            gaps = _history_gaps(history) or [
                "Supervisor 未返回有效的最终评估"
                if history
                else "Supervisor 无法形成有效的初始研究分工"
            ]
            decision = SupervisorDecision(
                action="finish",
                rationale="主管无法生成有效决策，使用现有研究资料结束",
                assignments=[],
                sufficient=False,
                gaps=gaps[:6],
            )
        return SupervisorOutcome(
            decision=decision,
            circuit_open=circuit_open,
            fallback_reason=reason_code,
        )

    async def _decide(
        self,
        question: str,
        history: list,
        *,
        phase: str,
        current_date: str,
        timezone: str,
        remaining_slots: int,
        can_dispatch: bool,
        max_assignments: int,
        circuit_open: bool,
    ) -> SupervisorOutcome:
        serialized = _normalized_history(history)
        if circuit_open:
            return self._fallback(
                serialized,
                can_dispatch=can_dispatch,
                max_assignments=max_assignments,
                reason_code="circuit_open",
                circuit_open=True,
            )
        bound = self.model.bind_tools([SUPERVISOR_TOOL])
        max_batch_size = min(
            int(getattr(self.runtime.settings, "multi_agent_max_batch_size", 3)),
            max(0, remaining_slots),
            max(0, max_assignments),
        )
        messages = supervisor_messages(
            question,
            serialized,
            phase=phase,
            current_date=current_date,
            timezone=timezone,
            remaining_slots=remaining_slots,
            max_batch_size=max_batch_size,
            can_dispatch=can_dispatch,
        )
        executed_ids = {
            item.get("id")
            for item in serialized
            if isinstance(item, dict)
        }
        executed_ids.discard(None)
        last_reason = "provider_failure"
        for attempt in range(2):
            try:
                try:
                    response = await self.runtime.invoke(bound, messages, "supervisor")
                except TimeoutError:
                    return self._fallback(
                        serialized,
                        can_dispatch=can_dispatch,
                        max_assignments=max_batch_size,
                        reason_code="provider_timeout",
                        circuit_open=True,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - sanitize Provider failures
                    return self._fallback(
                        serialized,
                        can_dispatch=can_dispatch,
                        max_assignments=max_batch_size,
                        reason_code="provider_failure",
                        circuit_open=False,
                    )
                calls = getattr(response, "tool_calls", [])
                if len(calls) > 1:
                    raise DecisionError("multiple_tool_calls")
                if not calls or calls[0].get("name") != "submit_supervisor_decision":
                    raise DecisionError("missing_tool_call")
                try:
                    decision = SupervisorDecision.model_validate(calls[0].get("args"))
                except (ValidationError, TypeError) as exc:
                    raise DecisionError("invalid_arguments") from exc
                if decision.action == "dispatch":
                    if not can_dispatch or remaining_slots <= 0:
                        raise DecisionError("dispatch_not_allowed")
                    try:
                        decision.validate_dispatch(
                            executed_ids=executed_ids,
                            max_batch_size=max_batch_size,
                        )
                    except ValueError as exc:
                        reason = (
                            "batch_too_large"
                            if "batch" in str(exc)
                            else "invalid_parent"
                        )
                        raise DecisionError(reason) from exc
                return SupervisorOutcome(decision=decision)
            except asyncio.CancelledError:
                raise
            except DecisionError as exc:
                last_reason = exc.reason_code
                if attempt == 0:
                    self.runtime.emit(
                        "supervisor.retry",
                        "主管决策格式无效，正在进行一次修复",
                        reason_code=last_reason,
                    )
                    messages = messages + [
                        HumanMessage(
                            content=(
                                f"Previous response was invalid ({last_reason}). "
                                "Return exactly one valid "
                                "submit_supervisor_decision tool call within the stated limits."
                            )
                        )
                    ]
                    continue
        return self._fallback(
            serialized,
            can_dispatch=can_dispatch,
            max_assignments=max_batch_size,
            reason_code=last_reason,
            circuit_open=False,
        )

    async def plan(
        self,
        question: str,
        *,
        current_date: str,
        timezone: str,
        remaining_slots: int,
        max_assignments: int,
    ) -> SupervisorOutcome:
        return await self._decide(
            question,
            [],
            phase="planning",
            current_date=current_date,
            timezone=timezone,
            remaining_slots=remaining_slots,
            can_dispatch=remaining_slots > 0 and max_assignments > 0,
            max_assignments=max_assignments,
            circuit_open=False,
        )

    async def replan(
        self,
        question: str,
        history: list[dict],
        *,
        current_date: str,
        timezone: str,
        remaining_slots: int,
        max_assignments: int,
        circuit_open: bool,
    ) -> SupervisorOutcome:
        return await self._decide(
            question,
            history,
            phase="replanning",
            current_date=current_date,
            timezone=timezone,
            remaining_slots=remaining_slots,
            can_dispatch=remaining_slots > 0 and max_assignments > 0,
            max_assignments=max_assignments,
            circuit_open=circuit_open,
        )

    async def decide(
        self,
        question: str,
        history: list,
        *,
        remaining_slots: int,
        can_dispatch: bool,
    ) -> SupervisorDecision:
        """Compatibility wrapper for the pre-graph adapter during migration."""
        now = datetime.now().astimezone()
        outcome = await self._decide(
            question,
            history,
            phase="replanning" if history else "planning",
            current_date=now.date().isoformat(),
            timezone=str(now.tzinfo),
            remaining_slots=remaining_slots,
            can_dispatch=can_dispatch,
            max_assignments=min(
                int(getattr(self.runtime.settings, "multi_agent_max_batch_size", 3)),
                remaining_slots,
            ),
            circuit_open=False,
        )
        return outcome.decision
