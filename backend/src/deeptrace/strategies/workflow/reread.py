"""Execute one bounded recovery read phase through the normal tool boundary."""

import asyncio
import hashlib

from langgraph.runtime import Runtime

from deeptrace.domain import (
    EvidenceLifecycleStatus,
    ResearchMode,
    ResearchTopicInput,
    ResearchTopicOutcome,
)
from deeptrace.harness.batch_collection import host_tools
from deeptrace.harness.context import HarnessContext
from deeptrace.harness.policies.execution import ExecutionPolicy
from deeptrace.observability.progress import emit_progress
from deeptrace.strategies.common import topic_error_gaps, validated_branch_context
from deeptrace.strategies.evidence_evaluation import require_evidence_contract
from deeptrace.strategies.source_reread import SourceReadAction
from deeptrace.strategies.workflow.state import WorkflowState
from deeptrace.tools.evidence_views import _merge


async def reread_node(
    state: WorkflowState, runtime: Runtime[HarnessContext], *,
    mode: ResearchMode = ResearchMode.WORKFLOW, caller_id: str = "workflow-graph",
) -> dict:
    requirements = require_evidence_contract(state)
    updates = {"reread_attempted": True, "reread_actions": [], "executed_steps": 1}
    context = runtime.context
    if state.get("reread_attempted") or getattr(
        context.model_gateway, "research_exhausted", False
    ):
        return {**updates, "diagnostic_gaps": ["reread_unavailable"]}
    gaps = {i.requirement_id for i in state["coverage"].items if i.status != "covered"}
    allowed = {r.id for r in requirements}
    actions, diagnostics, seen = [], [], set()
    for candidate in (state.get("reread_actions") or [])[:2]:
        try:
            action = SourceReadAction.model_validate(candidate)
            anchor = action.anchor
            record = await context.evidence_store.get(
                context.workspace_id, anchor.evidence_id
            )
            targets = action.target_requirement_ids
            if (
                anchor.range_key in seen
                or anchor.evidence_id not in (state.get("evidence_ids") or [])
                or (state.get("source_eligibility") or {}).get(anchor.evidence_id)
                == "ineligible"
                or record.status is not EvidenceLifecycleStatus.ACTIVE
                or record.version != anchor.version
                or record.content_hash != anchor.content_hash
                or anchor.end - anchor.start > 900
                or not targets
                or len(set(targets)) != len(targets)
                or not set(targets) <= allowed
            ):
                raise ValueError("invalid_reread_action")
            targets = [t for t in targets if t in gaps]
            if not targets:
                raise ValueError("covered_reread_action")
            seen.add(anchor.range_key)
            actions.append(
                action.model_copy(update={"target_requirement_ids": targets})
            )
        except Exception:  # noqa: BLE001 - fail closed per source; cancellation propagates
            diagnostics.append("reread_action_rejected")
    if not actions:
        return {**updates, "diagnostic_gaps": [*diagnostics, "reread_no_usable_action"]}
    identity = hashlib.sha256(
        "|".join(a.model_dump_json() for a in actions).encode()
    ).hexdigest()[:24]
    query = f"补读已有原文：{identity}"
    targets = list(dict.fromkeys(t for a in actions for t in a.target_requirement_ids))
    task = ResearchTopicInput(
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        query=query,
        mode=mode,
        caller_id=caller_id,
        **await validated_branch_context(
            {**state, "query": query, "target_requirement_ids": targets}, context
        ),
    )
    executed = await host_tools(
        {"topic_input": task},
        context,
        [
            (
                "read_evidence",
                {
                    "evidence_id": a.anchor.evidence_id,
                    "start": a.anchor.start,
                    "limit": a.anchor.end - a.anchor.start,
                },
            )
            for a in actions
        ],
        concurrency=2,
    )
    # A concurrently changed source or incomplete read cannot acquire preferred
    # status simply because the host requested a previously valid coordinate.
    anchors = []
    for action in actions:
        expected = action.anchor
        # The tool numbers <=500-character references before capturing reads.
        # Reconstitute a requested whole range only from a gapless union of
        # successful actual references at the same source/version/hash.
        ranges = _merge(
            [
                (a.start, a.end)
                for a in executed.get("read_anchors") or []
                if a.evidence_id == expected.evidence_id
                and a.version == expected.version
                and a.content_hash == expected.content_hash
                and expected.start <= a.start < a.end <= expected.end
            ]
        )
        if ranges == [(expected.start, expected.end)]:
            anchors.append(expected)
    if not anchors:
        diagnostics.append("batch_acquisition_incomplete")
    executed["stop_reason"] = executed.get("stop_reason") or (
        "completed" if anchors else "incomplete_plan"
    )
    agent = ExecutionPolicy(max_iterations=1).outcome(executed)
    if agent.status == "cancelled":
        raise asyncio.CancelledError()
    outcome = ResearchTopicOutcome(
        query=query,
        agent_outcome=agent,
        evidence_ids=agent.evidence_ids,
        read_anchors=anchors,
        read_anchor_diagnostics=executed.get("read_anchor_diagnostics") or [],
        research_finding_diagnostics=diagnostics,
        errors=executed.get("errors") or [],
        executed_steps=agent.executed_steps,
    )
    await emit_progress(
        context,
        "research.recovery.reread",
        target_requirement_ids=targets,
        read_count=len(anchors),
    )
    return {
        **updates,
        "topic_outcomes": [outcome],
        "reread_queries": [query],
        "diagnostic_gaps": [*diagnostics, *topic_error_gaps(outcome)],
        "executed_steps": 1 + agent.executed_steps,
    }
