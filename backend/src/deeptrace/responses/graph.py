"""Shared load → generate → validate topology for response subgraphs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from deeptrace.harness.prompts import task_messages
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
from deeptrace.harness.token_budget import (
    BudgetAllocation,
    Segment,
    SegmentPriority,
    TokenBudgetConfig,
    assemble_with_budget,
)
from deeptrace.responses.citations import (
    extract_citation_markers,
    validate_citations,
)
from deeptrace.responses.models import ResponseDraft
from deeptrace.responses.state import ResponseState


logger = logging.getLogger(__name__)

RESPONDER_ROLE = "responder"

# 角标是引用校验的唯一硬通货，写进每份 prompt，降低模型偶发不标 [n] 的概率。
CITATION_RULE = (
    "引用规则：每个事实性句子末尾都要标注其资料编号 [n]，n 只能取下面列出的编号；"
    "必须使用半角方括号写法（如 [1]），禁止使用【1】、［1］、（1）等其它形式。"
)
# 前端按纯文本渲染，Markdown 标题符号会原样显示成 "##"，必须在提示词层禁止，
# 并在输出层确定性剥离（两道保险，模型不听话时也不会漏）。
PLAIN_TEXT_RULE = (
    "格式规则：只输出纯文本，禁止使用 Markdown 标题符号（#、##、###）、"
    "星号加粗（**）或代码块；小节标题写成普通一行，例如「一、概述」。"
)
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}(?:[ \t]+|$)", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def strip_markdown_headings(text: str) -> str:
    """Remove leading Markdown heading markers and bold emphasis."""
    without_headings = _HEADING_RE.sub("", text)
    return _BOLD_RE.sub(r"\1", without_headings)


# 一次纠正性重试：首次输出无法解析或完全没有角标时，带着更严格的要求再要一次。
CORRECTIVE_SUFFIX = (
    "\n\n上一版输出未通过校验，请严格重做："
    '只输出一个 JSON 对象 {"content": "..."}，不要输出任何额外文字或代码块；'
    "content 中每个事实性句子末尾必须带半角方括号角标 [n]，"
    "n 只能取上面列出的资料编号，且不允许出现没有任何角标的成稿。"
)

# 输出不完整或超过篇幅上限时只纠偏一次，要求给出完整且不超限的成稿。
_SENTENCE_END = "。！？.!?…\n"
# 以这些符号结尾几乎可以确定是被截断的悬空句。
_DANGLING_END = "，,、：:；;（(【《「『-—"


def _length_corrective_suffix(max_chars: int) -> str:
    return (
        "\n\n上一版输出不完整或超过篇幅上限，请重新输出完整版本："
        f"全文不超过 {max_chars} 个字符，结尾必须是完整的句子，"
        '只输出一个 JSON 对象 {"content": "..."}，不要重复已有内容。'
    )


def _looks_incomplete(text: str) -> bool:
    """Conservative truncation signal: only flag clearly dangling endings."""
    stripped = re.sub(r"(\[\d+\])+\s*$", "", text.strip()).strip()
    if not stripped:
        return True
    return stripped[-1] in _DANGLING_END


def _cut_at_sentence(text: str, limit: int) -> str:
    """Cut at the last sentence boundary before ``limit`` (never mid-clause)."""
    if len(text) <= limit:
        return text
    window = text[:limit]
    floor = max(0, len(window) - 200)
    for index in range(len(window) - 1, floor - 1, -1):
        if window[index] in _SENTENCE_END:
            return window[: index + 1].rstrip()
    return window.rstrip()

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
        "正文必须分行分段：每 2 到 4 句构成一段，段落之间用空行分隔；"
        "涉及列举、对比或时间线时逐条换行，禁止把全部内容压成一个大段落。"
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


def _extract_content(raw_text: str) -> str:
    """Pull the content string out of the model's JSON envelope.

    Primary path is strict JSON; one tolerant fallback slices the outermost
    {...} block when the model wraps JSON in prose or a code fence remnant.
    """
    try:
        payload = json.loads(raw_text)
    except (TypeError, ValueError):
        start, end = raw_text.find("{"), raw_text.rfind("}")
        if start == -1 or end <= start:
            raise
        payload = json.loads(raw_text[start : end + 1])
    if not isinstance(payload, dict) or not isinstance(
        payload.get("content"), str
    ):
        raise ValueError("model payload is not a content object")
    return payload["content"]


_SOURCE_MIN_TOKENS = 200


def _build_prompt_segments(
    policy: ResponsePolicy,
    response_input: ResponseInput,
    sources: list[str],
    findings_lines: str,
    notes: str,
    *,
    corrective_suffix: str | None,
) -> list[Segment]:
    segments = [
        Segment(
            "instructions",
            f"{policy.instructions}\n{CITATION_RULE}\n{PLAIN_TEXT_RULE}\n\n",
            SegmentPriority.PINNED,
        ),
        Segment(
            "question",
            f"用户问题：{response_input.question}\n\n",
            SegmentPriority.PINNED,
        ),
    ]
    if notes:
        segments.append(
            Segment(
                "notes",
                f"背景记忆（用户偏好与已知结论）：\n{notes}\n\n",
                SegmentPriority.HIGH,
            )
        )
    segments.append(
        Segment(
            "findings",
            f"研究发现：\n{findings_lines or '（无）'}\n\n",
            SegmentPriority.HIGH,
        )
    )
    segments.append(
        Segment(
            "sources_header",
            "以下是本轮已加载的全部资料（编号即引用标记，禁止引用未列出的来源）：\n\n",
            SegmentPriority.PINNED,
        )
    )
    for index, source in enumerate(sources, 1):
        segments.append(
            Segment(
                f"source_{index}",
                f"{source}\n\n",
                SegmentPriority.NORMAL,
                min_tokens=_SOURCE_MIN_TOKENS,
            )
        )
    contract = '\n只输出 JSON：{"content": "..."}。'
    segments.append(
        Segment(
            "output_contract",
            contract + (corrective_suffix or ""),
            SegmentPriority.PINNED,
        )
    )
    return segments


def _compose_prompt(
    policy: ResponsePolicy,
    response_input: ResponseInput,
    sources: list[str],
    findings_lines: str,
    notes: str,
    *,
    corrective_suffix: str | None,
    budget_config: TokenBudgetConfig,
) -> tuple[str, BudgetAllocation]:
    segments = _build_prompt_segments(
        policy,
        response_input,
        sources,
        findings_lines,
        notes,
        corrective_suffix=corrective_suffix,
    )
    return assemble_with_budget(segments, budget_config)


async def _record_generation_observability(
    runtime: Runtime[HarnessContext],
    policy: ResponsePolicy,
    allocations: list[BudgetAllocation],
    output_truncated: bool,
    output_incomplete: bool,
) -> None:
    if allocations:
        summary = allocations[-1].summary()
        summary["response_mode"] = policy.mode.value
        # Always record the measurement at debug level so thresholds can be
        # tuned from real traffic; only actual trimming raises a visible event.
        logger.debug("response context budget", extra={"budget": summary})
        if allocations[-1].bound:
            logger.warning("response context budget applied: %s", summary)
            try:
                await runtime.context.event_sink.emit("response.budget", summary)
            except Exception:
                pass
    if output_truncated or output_incomplete:
        details = {
            "response_mode": policy.mode.value,
            "output_truncated": output_truncated,
            "output_incomplete": output_incomplete,
            "max_content_chars": policy.max_content_chars,
        }
        logger.warning("response output adjusted: %s", details)
        try:
            await runtime.context.event_sink.emit("response.truncated", details)
        except Exception:
            pass


def build_generate_node(
    policy: ResponsePolicy,
    budget_config: TokenBudgetConfig | None = None,
):
    budget = budget_config or TokenBudgetConfig()

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
        # 证据正文只读一次；纠正重试复用同一批材料，避免重复 IO。
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
        # context_notes are pre-bounded by the caller (24 entries, each
        # truncated); do not re-trim here or recent messages get cut
        notes = "\n".join(
            f"- {note}" for note in response_input.context_notes
        )

        allocations: list[BudgetAllocation] = []

        async def invoke_model(*, corrective_suffix: str | None = None) -> str:
            prompt, allocation = _compose_prompt(
                policy,
                response_input,
                sources,
                findings_lines,
                notes,
                corrective_suffix=corrective_suffix,
                budget_config=budget,
            )
            allocations.append(allocation)
            response = await runtime.context.model_gateway.invoke(
                role=RESPONDER_ROLE, messages=task_messages(instruction=policy.instructions, task=response_input.question, constraints=response_input.constraints, prompt=prompt)
            )
            content = strip_markdown_headings(
                _extract_content(_payload_text(response)).strip()
            ).strip()
            if not content:
                raise ValueError("model content is empty")
            return content

        async def fit_length(initial: str) -> tuple[str, bool, bool]:
            """One corrective retry for over-long or dangling output, then cut
            at a sentence boundary instead of silently slicing mid-sentence."""
            max_chars = policy.max_content_chars
            over = len(initial) > max_chars
            incomplete = _looks_incomplete(initial)
            if not over and not incomplete:
                return initial, False, False
            logger.warning(
                "responder output over_length=%s incomplete=%s; "
                "issuing one length corrective retry",
                over,
                incomplete,
            )
            try:
                retried = await invoke_model(
                    corrective_suffix=_length_corrective_suffix(max_chars)
                )
            except (ValidationError, ValueError, TypeError) as error:
                logger.warning(
                    "length corrective retry failed (%s); cutting deterministically",
                    type(error).__name__,
                )
                retried = ""
            candidate = retried or initial
            still_incomplete = _looks_incomplete(candidate)
            if len(candidate) > max_chars:
                return _cut_at_sentence(candidate, max_chars), True, still_incomplete
            return candidate, False, still_incomplete

        # 首次尝试
        try:
            content = await invoke_model()
        except (ValidationError, ValueError, TypeError) as first_error:
            logger.warning(
                "responder draft unparseable on first attempt (%s); "
                "issuing one corrective retry",
                type(first_error).__name__,
            )
            try:
                content = await invoke_model(corrective_suffix=CORRECTIVE_SUFFIX)
            except (ValidationError, ValueError, TypeError) as second_error:
                logger.warning(
                    "responder draft still unparseable after retry (%s); "
                    "falling back to evidence listing",
                    type(second_error).__name__,
                )
                return {"draft": None}

        # 零角标自愈：模型偶发不标 [n] 时，带严格要求重试一次
        if not extract_citation_markers(content):
            logger.warning(
                "responder draft carried no citation markers on first attempt; "
                "issuing one corrective retry"
            )
            try:
                repaired = await invoke_model(corrective_suffix=CORRECTIVE_SUFFIX)
                if extract_citation_markers(repaired):
                    content = repaired
                else:
                    logger.warning(
                        "responder retry still carries no citation markers; "
                        "validation gate will apply the evidence fallback"
                    )
                    content = repaired
            except (ValidationError, ValueError, TypeError) as retry_error:
                logger.warning(
                    "citation corrective retry failed (%s); keeping first draft",
                    type(retry_error).__name__,
                )

        content, output_truncated, output_incomplete = await fit_length(content)
        await _record_generation_observability(
            runtime,
            policy,
            allocations,
            output_truncated,
            output_incomplete,
        )
        return {
            "draft": ResponseDraft(response_mode=policy.mode, content=content)
        }

    return generate_node


def build_validate_node(policy: ResponsePolicy):
    async def validate_node(state: ResponseState) -> dict[str, Any]:
        existing = state.get("outcome")
        if existing is not None:
            return {"outcome": existing}
        loaded = list(state.get("loaded_evidence") or [])
        draft = state.get("draft")
        if draft is None:
            logger.warning(
                "response generation failed after retries (%d evidence loaded); "
                "returning evidence-backed partial",
                len(loaded),
            )
            return {
                "outcome": _fallback_outcome(
                    policy, loaded, reason="generation_failed"
                )
            }
        outcome = validate_citations(
            draft, loaded_evidence_ids=[record.id for record in loaded]
        )
        if outcome.partial_reason == "no_supported_citations":
            logger.warning(
                "draft has no supported citation markers (%d evidence loaded, "
                "markers seen: %s); replacing with evidence-backed partial",
                len(loaded),
                extract_citation_markers(draft.content),
            )
            outcome = _fallback_outcome(
                policy, loaded, reason="no_supported_citations"
            )
        return {"outcome": outcome}

    return validate_node


def build_response_graph(
    policy: ResponsePolicy,
    checkpointer=None,
    *,
    budget_config: TokenBudgetConfig | None = None,
) -> CompiledStateGraph:
    builder = StateGraph(ResponseState, context_schema=HarnessContext)
    builder.add_node("load_evidence", load_evidence_node)
    builder.add_node(
        "generate", build_generate_node(policy, budget_config=budget_config)
    )
    builder.add_node("validate", build_validate_node(policy))
    builder.add_edge(START, "load_evidence")
    builder.add_edge("load_evidence", "generate")
    builder.add_edge("generate", "validate")
    builder.add_edge("validate", END)
    return builder.compile(checkpointer=checkpointer)


def build_answer_graph(
    budget_config: TokenBudgetConfig | None = None, *, checkpointer=None
) -> CompiledStateGraph:
    return build_response_graph(
        ANSWER_POLICY, checkpointer=checkpointer, budget_config=budget_config
    )


def build_brief_graph(
    budget_config: TokenBudgetConfig | None = None, *, checkpointer=None
) -> CompiledStateGraph:
    return build_response_graph(
        BRIEF_POLICY, checkpointer=checkpointer, budget_config=budget_config
    )


def build_report_graph(
    budget_config: TokenBudgetConfig | None = None, *, checkpointer=None
) -> CompiledStateGraph:
    return build_response_graph(
        REPORT_POLICY, checkpointer=checkpointer, budget_config=budget_config
    )
