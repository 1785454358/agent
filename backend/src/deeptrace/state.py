"""LangGraph State 定义及其可测试的 reducer。"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage

from deeptrace.models import (
    ContextAudit,
    DocumentChunk,
    PendingFetch,
    RawDocument,
    ResearchNote,
    RoundTokenMetrics,
)


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """合并节点增量，键冲突时采用最新值且不修改输入。"""
    return {**left, **right}


def append_unique(left: list[str], right: list[str]) -> list[str]:
    """按首次出现顺序追加并去重，适用于历史查询。"""
    return list(dict.fromkeys([*left, *right]))


class GraphState(TypedDict):
    """研究图的可序列化状态；向量由进程内 runtime 单独持有。"""

    user_query: str
    active_query: str
    messages: list[BaseMessage]
    documents: Annotated[dict[str, RawDocument], merge_dicts]
    chunks: Annotated[dict[str, DocumentChunk], merge_dicts]
    notes: Annotated[dict[str, ResearchNote], merge_dicts]
    queries: Annotated[list[str], append_unique]
    pending_fetches: list[PendingFetch]
    pending_tool_order: list[str]
    tool_outputs: Annotated[dict[str, str], merge_dicts]
    events: Annotated[list[str], operator.add]
    token_metrics: Annotated[list[RoundTokenMetrics], operator.add]
    context_audits: Annotated[list[ContextAudit], operator.add]
    step_count: int
    extension_granted: bool
    recent_new_note_count: int
    unresolved_gaps: list[str]
    final_answer: str
