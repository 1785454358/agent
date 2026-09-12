"""Shared load → generate → validate topology for response subgraphs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from pydantic import ValidationError

from deeptrace.domain import (
    CitationRef,
    Evidence,
    ResponseInput,
    ResponseMode,
    ResponseOutcome,
)
from deeptrace.harness.context import HarnessContext
from deeptrace.responses.citations import validate_citations
from deeptrace.responses.models import ResponseDraft
from deeptrace.responses.state import ResponseState


RESPONDER_ROLE = "responder"

MAX_ANSWER_CONTENT = 2_000
MAX_BRIEF_CONTENT = 8_000
MAX_REPORT_CONTENT = 50_000
ANSWER_SOURCE_CHARS = 3_000
BRIEF_SOURCE_CHARS = 6_000
REPORT_SOURCE_CHARS = 20_000


@dataclass(frozen=True)
class ResponsePolicy:
    mode: ResponseMode
    instructions: str
    max_content_chars: int
    per_source_chars: int


ANSWER_POLICY = ResponsePolicy(
    mode=ResponseMode.ANSWER,
    instructions=(
        "用简洁自然的中文直接回答用户问题，不要分节标题，不要复述问题。"
        "引用资料时使用方括号标记，例如 [1]。"
    ),
    max_content_chars=MAX_ANSWER_CONTENT,
    per_source_chars=ANSWER_SOURCE_CHARS,
)

BRIEF_POLICY = ResponsePolicy(
    mode=ResponseMode.BRIEF,
    instructions=(
        "输出一份结构化摘要：使用短小标题或要点列表呈现对比与阶段性结论，"
        "总长度保持克制。引用资料时使用方括号标记，例如 [1]。"
    ),
    max_content_chars=MAX_BRIEF_CONTENT,
    per_source_chars=BRIEF_SOURCE_CHARS,
)

REPORT_POLICY = ResponsePolicy(
    mode=ResponseMode.REPORT,
    instructions=(
        "生成一份正式报告：包含概述、分节论述与结论，论述需逐条对应资料证据。"
        "引用资料时使用方括号标记，例如 [1]。"
    ),
    max_content_chars=MAX_REPORT_CONTENT,
    per_source_chars=REPORT_SOURCE_CHARS,
)


def _response_input(state: ResponseState) -> ResponseInput:
    return ResponseInput.model_validate(state["response_input"])


async def load_evidence_node(
    state: ResponseState, runtime: Runtime[HarnessContext]
) -> dict[str, Any]:
    response_input = _response_input(state)
    tenant = runtime.context.workspace_id
    loaded: list[Evidence] = []
    seen: set[str] = set()
    for evidence_id in response_input.active_evidence_ids:
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        try:
            record = await runtime.context.evidence_store.get(tenant, evidence_id)
        except (KeyError, ValueError):
            continue
        loaded.append(record)
    return {"loaded_evidence": loaded}


def _payload_text(response: Any) -> str:
    if isinstance(response, str):
        text = response
    elif hasattr(response, "content"):
        content = response.content
        text = content if isinstance(content, str) else str(content)
    else:
        text = str(response)
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip().endswith("```"):
            lines = lines[1:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _source_block(evidence: Evidence, body: str, marker: str, limit: int) -> str:
    excerpt = body[:limit]
    return (
        f"{marker} id={evidence.id}\n"
        f"标题：{evidence.title}\n"
        f"来源：{evidence.canonical_url}\n"
        f"正文摘录：\n{excerpt}"
    )


def _fallback_outcome(
    policy: ResponsePolicy, loaded: list[Evidence], reason: str
) -> ResponseOutcome:
    lines: list[str] = []
    citations: list[CitationRef] = []
    for index, record in enumerate(loaded, 1):
        marker = f"[{index}]"
        lines.append(f"{marker} {record.title}（{record.canonical_url}）")
        citations.append(CitationRef(evidence_id=record.id, marker=marker))
    content = (
        "本次研究未能生成有引用支持的完整内容。以下是可追溯的资料来源：\n"
        + "\n".join(lines)
    )
    if len(content) > policy.max_content_chars:
        content = content[: policy.max_content_chars]
    return ResponseOutcome(
        response_mode=policy.mode,
        content=content,
        citations=citations,
        cited_evidence_ids=[citation.evidence_id for citation in citations],
        partial_reason=reason,
    )


def build_generate_node(policy: ResponsePolicy):
    async def generate_node(
        state: ResponseState, runtime: Runtime[HarnessContext]
    ) -> dict[str, Any]:
        loaded = list(state.get("loaded_evidence") or [])
        if not loaded:
            return {
                "outcome": _fallback_outcome(policy, loaded, reason="no_evidence")
            }

        response_input = _response_input(state)
        tenant = runtime.context.workspace_id
        sources: list[str] = []
        for index, record in enumerate(loaded, 1):
            try:
                body = await runtime.context.evidence_store.read_body(
                    tenant, record.id
                )
            except (KeyError, ValueError):
                body = ""
            sources.append(
                _source_block(record, body, f"[{index}]", policy.per_source_chars)
            )
        findings_lines = "\n".join(
            f"- {finding.claim}（{', '.join(finding.evidence_ids)}）"
            for finding in (response_input.research_outcome.findings if response_input.research_outcome else [])
        )
        prompt = (
            f"{policy.instructions}\n\n"
            f"用户问题：{response_input.question}\n\n"
            f"研究发现：\n{findings_lines or '（无）'}\n\n"
            "以下是本轮已加载的全部资料（编号即引用标记，禁止引用未列出的来源）：\n\n"
            + "\n\n".join(sources)
            + '\n\n只输出 JSON：{"content": "..."}。'
        )
        try:
            response = await runtime.context.model_gateway.invoke(
                role=RESPONDER_ROLE, messages=[HumanMessage(content=prompt)]
            )
            payload = json.loads(_payload_text(response))
            if not isinstance(payload, dict) or not isinstance(
                payload.get("content"), str
            ):
                raise ValueError("model payload is not a content object")
            content = payload["content"].strip()[: policy.max_content_chars]
            if not content:
                raise ValueError("model content is empty")
            draft = ResponseDraft(response_mode=policy.mode, content=content)
        except (ValidationError, ValueError, TypeError):
            return {"draft": None}
        return {"draft": draft}

    return generate_node


def build_validate_node(policy: ResponsePolicy):
    async def validate_node(state: ResponseState) -> dict[str, Any]:
        existing = state.get("outcome")
        if existing is not None:
            return {"outcome": existing}
        loaded = list(state.get("loaded_evidence") or [])
        draft = state.get("draft")
        if draft is None:
            return {
                "outcome": _fallback_outcome(
                    policy, loaded, reason="generation_failed"
                )
            }
        outcome = validate_citations(
            draft, loaded_evidence_ids=[record.id for record in loaded]
        )
        if outcome.partial_reason == "no_supported_citations":
            outcome = _fallback_outcome(
                policy, loaded, reason="no_supported_citations"
            )
        return {"outcome": outcome}

    return validate_node


def build_response_graph(policy: ResponsePolicy, checkpointer=None) -> CompiledStateGraph:
    builder = StateGraph(ResponseState, context_schema=HarnessContext)
    builder.add_node("load_evidence", load_evidence_node)
    builder.add_node("generate", build_generate_node(policy))
    builder.add_node("validate", build_validate_node(policy))
    builder.add_edge(START, "load_evidence")
    builder.add_edge("load_evidence", "generate")
    builder.add_edge("generate", "validate")
    builder.add_edge("validate", END)
    return builder.compile(checkpointer=checkpointer)


def build_answer_graph(checkpointer=None) -> CompiledStateGraph:
    return build_response_graph(ANSWER_POLICY, checkpointer=checkpointer)


def build_brief_graph(checkpointer=None) -> CompiledStateGraph:
    return build_response_graph(BRIEF_POLICY, checkpointer=checkpointer)


def build_report_graph(checkpointer=None) -> CompiledStateGraph:
    return build_response_graph(REPORT_POLICY, checkpointer=checkpointer)
