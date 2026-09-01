"""核验后 Claim Writer 与确定性引用渲染。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import json_repair
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from deeptrace.agent._shared import add_usage, message_text, message_usage
from deeptrace.models import (
    Claim,
    Evidence,
    ResearchPlan,
    SectionResult,
    Source,
    TokenUsage,
    VerificationGap,
    VerificationResult,
)
from deeptrace.prompts.writer import build_writer_messages


class ReportBlock(BaseModel):
    kind: Literal["fact", "analysis", "limitation"]
    text: str = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)


class VerifiedReportSection(BaseModel):
    heading: str = Field(min_length=1)
    blocks: list[ReportBlock] = Field(default_factory=list)


class VerifiedWriterOutput(BaseModel):
    title: str = Field(min_length=1)
    sections: list[VerifiedReportSection] = Field(default_factory=list)
    used_claim_ids: list[str] = Field(default_factory=list)


def parse_writer_output(raw: str) -> VerifiedWriterOutput:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Writer 未返回 JSON 对象")
    try:
        payload = json_repair.loads(raw[start : end + 1])
        return VerifiedWriterOutput.model_validate(payload)
    except Exception as exc:
        raise ValueError("Writer JSON 无法校验") from exc


def is_language_consistent(markdown: str, language: str) -> bool:
    cjk = len(re.findall(r"[㐀-鿿]", markdown))
    latin = len(re.findall(r"[A-Za-z]", markdown))
    return cjk >= max(8, latin // 5) if language == "zh-CN" else latin >= max(8, cjk)


_TIME_QUALIFIERS = (
    "后续",
    "回顾",
    "截至",
    "后来",
    "不属于",
    "retrospective",
    "subsequent",
    "as of",
    "outside the period",
)
_UNCERTAINTY_MARKERS = (
    "现有证据显示",
    "材料尚不足",
    "证据有限",
    "可能",
    "suggests",
    "insufficient evidence",
)


def find_unqualified_year_mentions(
    markdown: str, start_year: int, end_year: int
) -> list[int]:
    body = markdown.split("## 来源", 1)[0]
    found: set[int] = set()
    for sentence in re.split(r"[。！？\n]", body):
        lower = sentence.lower()
        if any(term in lower for term in _TIME_QUALIFIERS):
            continue
        for value in re.findall(r"\b20\d{2}\b", sentence):
            year = int(value)
            if year < start_year or year > end_year:
                found.add(year)
    return sorted(found)


def validate_writer_output(
    output: VerifiedWriterOutput,
    verification_results: Mapping[str, VerificationResult],
) -> list[str]:
    """验证每个报告块是否只使用其 verdict 允许的 Claim。"""
    violations: list[str] = []
    for section in output.sections:
        for block in section.blocks:
            if block.kind == "fact" and not block.claim_ids:
                violations.append("fact_without_claim")
            for claim_id in block.claim_ids:
                result = verification_results.get(claim_id)
                if result is None:
                    violations.append("unknown_claim_id")
                    continue
                if block.kind == "fact" and result.verdict != "verified":
                    violations.append("claim_not_writable")
                if block.kind == "analysis" and result.verdict not in {
                    "verified",
                    "partially_supported",
                }:
                    violations.append("claim_not_writable")
                if (
                    block.kind == "analysis"
                    and result.verdict == "partially_supported"
                    and not any(
                        marker in block.text.lower()
                        for marker in _UNCERTAINTY_MARKERS
                    )
                ):
                    violations.append("partial_without_uncertainty")
    for claim_id in output.used_claim_ids:
        if claim_id not in verification_results:
            violations.append("unknown_claim_id")
    return list(dict.fromkeys(violations))


def _used_ids_from_blocks(output: VerifiedWriterOutput) -> list[str]:
    return list(
        dict.fromkeys(
            claim_id
            for section in output.sections
            for block in section.blocks
            if block.kind in {"fact", "analysis"}
            for claim_id in block.claim_ids
        )
    )


def sources_from_used_claims(
    used_claim_ids: Sequence[str],
    claims: Mapping[str, Claim],
    evidence: Mapping[str, Evidence],
    sources: Mapping[str, Source],
) -> list[str]:
    """沿 Claim → Evidence → Source 按首次使用顺序返回 URL。"""
    urls: list[str] = []
    for claim_id in used_claim_ids:
        claim = claims.get(claim_id)
        if claim is None:
            continue
        for evidence_id in claim.evidence_ids:
            item = evidence.get(evidence_id)
            source = sources.get(item.source_id) if item else None
            if source is not None and source.final_url not in urls:
                urls.append(source.final_url)
    return urls


def render_verified_output(
    output: VerifiedWriterOutput,
    claims: Mapping[str, Claim],
    verification_results: Mapping[str, VerificationResult],
    evidence: Mapping[str, Evidence],
    sources: Mapping[str, Source],
) -> str:
    """本地添加稳定脚注，模型无法伪造来源 URL。"""
    footnote_numbers: dict[str, int] = {}
    footnotes: list[str] = []
    lines = [f"# {output.title}"]
    for section in output.sections:
        lines.extend(["", f"## {section.heading}", ""])
        for block in section.blocks:
            refs: list[str] = []
            if block.kind in {"fact", "analysis"}:
                for claim_id in block.claim_ids:
                    if claim_id not in footnote_numbers:
                        footnote_numbers[claim_id] = len(footnote_numbers) + 1
                    refs.append(f"[^{footnote_numbers[claim_id]}]")
            prefix = "- " if block.kind != "limitation" else "- 局限："
            lines.append(prefix + block.text + "".join(refs))

    for claim_id, number in footnote_numbers.items():
        claim = claims.get(claim_id)
        result = verification_results.get(claim_id)
        if claim is None or result is None:
            continue
        evidence_ids = (
            result.supporting_evidence_ids or claim.evidence_ids
        )
        citations: list[str] = []
        for evidence_id in evidence_ids:
            item = evidence.get(evidence_id)
            source = sources.get(item.source_id) if item else None
            if (
                item is None
                or source is None
                or item.location_status != "exact"
            ):
                continue
            citations.append(
                f"“{item.quote}” — [{source.title}]({source.final_url})"
            )
        footnotes.append(
            f"[^{number}]: " + ("；".join(citations) or "证据血缘缺失")
        )
    if footnotes:
        lines.extend(["", "## 证据引用", "", *footnotes])
    urls = sources_from_used_claims(
        output.used_claim_ids, claims, evidence, sources
    )
    if urls:
        lines.extend(["", "## 来源", ""])
        lines.extend(f"- {url}" for url in urls)
    return "\n".join(lines)


def render_fallback_report(
    plan: ResearchPlan,
    sections: Sequence[SectionResult],
    claims: Sequence[Claim],
    results: Mapping[str, VerificationResult],
    gaps: Sequence[VerificationGap],
    termination_reason: str,
) -> VerifiedWriterOutput:
    """模型不可用时只输出已验证事实，其余内容明确列为局限。"""
    claims_by_section: dict[str, list[Claim]] = {}
    for claim in claims:
        claims_by_section.setdefault(claim.section_id, []).append(claim)
    rendered_sections: list[VerifiedReportSection] = []
    used: list[str] = []
    for section in sections:
        blocks: list[ReportBlock] = []
        for claim in claims_by_section.get(section.section_id, []):
            result = results.get(claim.claim_id)
            if result is not None and result.verdict == "verified":
                blocks.append(
                    ReportBlock(
                        kind="fact",
                        text=claim.text,
                        claim_ids=[claim.claim_id],
                    )
                )
                used.append(claim.claim_id)
        if not blocks:
            blocks.append(
                ReportBlock(
                    kind="limitation",
                    text=(
                        f"本节没有可写的 verified Claim；"
                        f"运行状态为 {termination_reason}。"
                    ),
                )
            )
        rendered_sections.append(
            VerifiedReportSection(heading=section.title, blocks=blocks)
        )
    if gaps and rendered_sections:
        rendered_sections[-1].blocks.append(
            ReportBlock(
                kind="limitation",
                text="仍有未解决证据缺口：" + "；".join(
                    gap.description for gap in gaps
                ),
            )
        )
    return VerifiedWriterOutput(
        title=plan.objective,
        sections=rendered_sections,
        used_claim_ids=list(dict.fromkeys(used)),
    )


class WriterAgent:
    """结构化写作失败时重试一次，再执行确定性安全降级。"""

    def __init__(self, model: Any) -> None:
        self._model = model

    async def awrite(
        self,
        *,
        plan: ResearchPlan,
        sections: Sequence[SectionResult],
        claims: Sequence[Claim],
        verification_results: Mapping[str, VerificationResult],
        evidence: Mapping[str, Evidence],
        sources: Mapping[str, Source],
        gaps: Sequence[VerificationGap],
        termination_reason: str,
    ) -> tuple[VerifiedWriterOutput, TokenUsage, bool]:
        writable = [
            claim
            for claim in claims
            if verification_results.get(claim.claim_id)
            and verification_results[claim.claim_id].verdict
            in {"verified", "partially_supported"}
        ]
        if not writable:
            return (
                render_fallback_report(
                    plan,
                    sections,
                    claims,
                    verification_results,
                    gaps,
                    termination_reason,
                ),
                TokenUsage(),
                True,
            )
        messages = build_writer_messages(
            plan=plan,
            sections=sections,
            claims=claims,
            verification_results=verification_results,
            evidence=evidence,
            sources=sources,
            gaps=gaps,
            termination_reason=termination_reason,
        )
        total = TokenUsage()
        current_messages = list(messages)
        for attempt in range(2):
            try:
                response = await self._model.ainvoke(current_messages)
                total = add_usage(total, message_usage(response))
                parsed = parse_writer_output(message_text(response))
                clean = parsed.model_copy(
                    update={"used_claim_ids": _used_ids_from_blocks(parsed)}
                )
                violations = validate_writer_output(
                    clean, verification_results
                )
                if violations:
                    if attempt == 0:
                        current_messages = [
                            *messages,
                            response,
                            HumanMessage(
                                content="请纠正后重新输出 JSON：" + "；".join(violations)
                            ),
                        ]
                        continue
                    raise ValueError("Writer Claim 权限校验失败")
                return clean, total, False
            except Exception:
                continue
        return (
            render_fallback_report(
                plan,
                sections,
                claims,
                verification_results,
                gaps,
                termination_reason,
            ),
            total,
            True,
        )
