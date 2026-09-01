"""LangGraph State 定义及其可测试的 reducer。"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage

from deeptrace.models import (
    Claim,
    ContextAudit,
    DocumentChunk,
    Evidence,
    PendingFetch,
    RawDocument,
    ResearchNote,
    ResearchPlan,
    RoundTokenMetrics,
    RunEvent,
    SectionResult,
    Source,
    TaskCompletion,
    TaskCoverage,
    TaskVerificationSummary,
    TokenUsage,
    UsageBreakdown,
    VerificationGap,
    VerificationResult,
    add_token_usages,
)


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """合并节点增量，键冲突时采用最新值且不修改输入。"""
    return {**left, **right}


def append_unique(left: list[str], right: list[str]) -> list[str]:
    """按首次出现顺序追加并去重，适用于历史查询。"""
    return list(dict.fromkeys([*left, *right]))


def merge_token_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
    """累加独立模型调用的用量，并保持 reducer 输入不可变。"""
    return TokenUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )


def merge_usage_breakdown(left: UsageBreakdown, right: UsageBreakdown) -> UsageBreakdown:
    return UsageBreakdown(
        planner=add_token_usages(left.planner, right.planner),
        researcher=add_token_usages(left.researcher, right.researcher),
        compression=add_token_usages(left.compression, right.compression),
        writer=add_token_usages(left.writer, right.writer),
        claim_extractor=add_token_usages(
            left.claim_extractor, right.claim_extractor
        ),
        verifier=add_token_usages(left.verifier, right.verifier),
    )


class GraphState(TypedDict):
    """研究图的可序列化状态；向量由进程内 runtime 单独持有。"""

    user_query: str
    active_query: str
    messages: list[BaseMessage]
    documents: Annotated[dict[str, RawDocument], merge_dicts]
    chunks: Annotated[dict[str, DocumentChunk], merge_dicts]
    notes: Annotated[dict[str, ResearchNote], merge_dicts]
    sources: Annotated[dict[str, Source], merge_dicts]
    evidence: Annotated[dict[str, Evidence], merge_dicts]
    claims: Annotated[dict[str, Claim], merge_dicts]
    verification_results: Annotated[
        dict[str, VerificationResult], merge_dicts
    ]
    verification_gaps: Annotated[dict[str, VerificationGap], merge_dicts]
    task_verification: Annotated[
        dict[str, TaskVerificationSummary], merge_dicts
    ]
    queries: Annotated[list[str], append_unique]
    pending_fetches: list[PendingFetch]
    pending_tool_order: list[str]
    tool_outputs: Annotated[dict[str, str], merge_dicts]
    research_plan: ResearchPlan | None
    current_task_index: int
    task_coverages: Annotated[dict[str, TaskCoverage], merge_dicts]
    section_results: Annotated[dict[str, SectionResult], merge_dicts]
    pending_task_completion: TaskCompletion | None
    verification_task_id: str | None
    verification_mode: Literal["initial", "supplement", "done"]
    verification_tool_rounds: int
    force_finalize: bool
    events: Annotated[list[RunEvent], operator.add]
    started_at: str
    fetched_page_count: Annotated[int, operator.add]
    api_token_count: Annotated[int, operator.add]
    estimated_cost_usd: Annotated[float, operator.add]
    provider_usage: Annotated[TokenUsage, merge_token_usage]
    role_usage: Annotated[UsageBreakdown, merge_usage_breakdown]
    used_note_ids: list[str]
    used_claim_ids: list[str]
    token_metrics: Annotated[list[RoundTokenMetrics], operator.add]
    context_audits: Annotated[list[ContextAudit], operator.add]
    step_count: int
    extension_granted: bool
    recent_new_note_count: int
    unresolved_gaps: list[str]
    final_answer: str
    termination_reason: str
