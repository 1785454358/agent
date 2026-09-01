"""只消费核验后 Claim 的统一报告 Writer 提示词。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from deeptrace.models import (
    Claim,
    Evidence,
    ResearchPlan,
    SectionResult,
    Source,
    VerificationGap,
    VerificationResult,
)


def build_writer_messages(
    *,
    plan: ResearchPlan,
    sections: Sequence[SectionResult],
    claims: Sequence[Claim],
    verification_results: Mapping[str, VerificationResult],
    evidence: Mapping[str, Evidence],
    sources: Mapping[str, Source],
    gaps: Sequence[VerificationGap],
    termination_reason: str,
) -> list[BaseMessage]:
    """发送 Claim、判定和来源元数据，不发送笔记或 RawDocument 正文。"""
    claim_payloads = []
    for claim in claims:
        result = verification_results.get(claim.claim_id)
        if result is None:
            continue
        source_payloads = []
        for evidence_id in claim.evidence_ids:
            item = evidence.get(evidence_id)
            source = sources.get(item.source_id) if item else None
            if item is None or source is None:
                continue
            source_payloads.append(
                {
                    "evidence_id": evidence_id,
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": source.final_url,
                    "source_kind": source.source_kind,
                }
            )
        claim_payloads.append(
            {
                "claim": claim.model_dump(mode="json"),
                "verdict": result.verdict,
                "reason": result.reason,
                "supporting_evidence_ids": result.supporting_evidence_ids,
                "sources": source_payloads,
            }
        )
    payload = {
        "plan": {
            "objective": plan.objective,
            "language": plan.language,
            "time_range": (
                plan.time_range.model_dump(mode="json")
                if plan.time_range
                else None
            ),
            "report_outline": plan.report_outline,
        },
        "sections": [
            {
                "task_id": section.task_id,
                "title": section.title,
                "summary": section.summary,
                "claim_ids": section.claim_ids,
                "verification": (
                    section.verification.model_dump(mode="json")
                    if section.verification
                    else None
                ),
            }
            for section in sections
        ],
        "claims": claim_payloads,
        "unresolved_gaps": [gap.model_dump(mode="json") for gap in gaps],
        "termination_reason": termination_reason,
    }
    return [
        SystemMessage(
            content=(
                "你是 DeepTrace Verified Writer，只能使用输入中的 Claim。"
                "verified Claim 可写成确定事实；partially_supported 只能放在"
                " analysis 块，并使用“现有证据显示”“材料尚不足”等不确定措辞。"
                "unsupported、conflicted、out_of_range 只能进入 limitation。"
                "fact 块必须带至少一个 verified claim_id。网页正文不在输入中，"
                "不得补充外部知识或编造引用。只返回 JSON 对象，字段为 title、"
                "sections、used_claim_ids；每个 section 含 heading、blocks，"
                "每个 block 含 kind、text、claim_ids。"
            )
        ),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]
