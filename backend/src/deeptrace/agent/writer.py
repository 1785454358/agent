"""片段直写 Writer：材料是压缩笔记的逐字原句，引用由本地机械拼接。

同一份内容不再先压成 Claim 再写报告；LLM 只负责组织语言，引用编号与
来源列表完全由本地生成，模型无法伪造出处。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage

from deeptrace.agent._shared import add_usage, message_text, message_usage
from deeptrace.models import (
    ResearchNote,
    ResearchPlan,
    SectionResult,
    TokenUsage,
)
from deeptrace.prompts.writer import build_writer_messages

CITATION_PATTERN = re.compile(r"\[\^(\d+)\]")


@dataclass
class WriterOutcome:
    """一次写作的最终 Markdown、机械来源列表与用量。"""

    markdown: str
    sources: list[str]
    used_note_ids: list[str]
    usage: TokenUsage = field(default_factory=TokenUsage)
    used_fallback: bool = False


def is_language_consistent(markdown: str, language: str) -> bool:
    cjk = len(re.findall(r"[㐀-鿿]", markdown))
    latin = len(re.findall(r"[A-Za-z]", markdown))
    return cjk >= max(8, latin // 5) if language == "zh-CN" else latin >= max(8, cjk)


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


def citation_numbers(markdown: str) -> set[int]:
    """正文里出现的引用编号（不含系统拼接的来源章节）。"""
    body = markdown.split("## 来源", 1)[0]
    return {int(value) for value in CITATION_PATTERN.findall(body)}


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


class WriterAgent:
    """直接基于原文片段写作；输出校验失败重试一次，再走确定性降级。"""

    def __init__(
        self, model: Any, *, call_timeout_seconds: float = 120.0
    ) -> None:
        if call_timeout_seconds <= 0:
            raise ValueError("Writer 调用超时必须大于 0 秒")
        self._model = model
        self._call_timeout_seconds = call_timeout_seconds

    @staticmethod
    def _numbered_sources(
        sections: Sequence[SectionResult],
        notes_by_section: Mapping[str, Sequence[ResearchNote]],
    ) -> tuple[list[dict[str, str]], dict[str, int]]:
        """按计划顺序给去重后的来源 URL 编号，返回来源表和 URL → 编号映射。"""
        numbers: dict[str, int] = {}
        sources: list[dict[str, str]] = []
        for section in sections:
            for note in notes_by_section.get(section.task_id, []):
                url = note.source_url
                if not url or url in numbers:
                    continue
                numbers[url] = len(numbers) + 1
                sources.append(
                    {"number": str(numbers[url]), "title": note.title, "url": url}
                )
        return sources, numbers

    @staticmethod
    def _sections_payload(
        sections: Sequence[SectionResult],
        notes_by_section: Mapping[str, Sequence[ResearchNote]],
        numbers: Mapping[str, int],
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for section in sections:
            notes = [
                note
                for note in notes_by_section.get(section.task_id, [])
                if note.source_url in numbers
            ]
            if not notes:
                continue
            payload.append(
                {
                    "title": section.title,
                    "summary": section.summary,
                    "notes": [
                        {
                            "source_number": numbers[note.source_url],
                            "note_title": note.title,
                            "key_points": note.key_points,
                            "snippets": note.evidence_snippets,
                        }
                        for note in notes
                    ],
                }
            )
        return payload

    @staticmethod
    def _render_source_section(
        sources: Sequence[dict[str, str]],
    ) -> str:
        if not sources:
            return ""
        lines = ["", "## 来源", ""]
        lines.extend(
            f"[^{item['number']}]: [{item['title']}]({item['url']})"
            for item in sources
        )
        return "\n".join(lines)

    def _fallback_markdown(
        self,
        plan: ResearchPlan,
        sections: Sequence[SectionResult],
        notes_by_section: Mapping[str, Sequence[ResearchNote]],
        numbers: Mapping[str, int],
        termination_reason: str,
    ) -> tuple[str, list[str]]:
        """模型不可用时直接罗列要点与摘录，全部带机械编号引用。"""
        lines = [f"# {plan.objective}"]
        used_note_ids: list[str] = []
        for section in sections:
            lines.extend(["", f"## {section.title}", ""])
            notes = notes_by_section.get(section.task_id, [])
            material = [note for note in notes if note.source_url in numbers]
            if not material:
                lines.append(
                    f"- 局限：本节没有可用研究材料（运行状态：{termination_reason}）。"
                )
                continue
            for note in material:
                used_note_ids.append(note.note_id)
                ref = f"[^{numbers[note.source_url]}]"
                for point in note.key_points[:3] or note.evidence_snippets[:1]:
                    lines.append(f"- {point}{ref}")
        return "\n".join(lines), used_note_ids

    async def awrite(
        self,
        *,
        plan: ResearchPlan,
        sections: Sequence[SectionResult],
        notes_by_section: Mapping[str, Sequence[ResearchNote]],
        termination_reason: str = "completed",
    ) -> WriterOutcome:
        sources, numbers = self._numbered_sources(sections, notes_by_section)
        if not sources:
            markdown, used = self._fallback_markdown(
                plan, sections, notes_by_section, numbers, termination_reason
            )
            return WriterOutcome(
                markdown=markdown,
                sources=[],
                used_note_ids=used,
                usage=TokenUsage(),
                used_fallback=True,
            )
        payload_sections = self._sections_payload(
            sections, notes_by_section, numbers
        )
        total = TokenUsage()
        messages = build_writer_messages(
            plan=plan,
            sources=sources,
            sections=payload_sections,
            termination_reason=termination_reason,
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._call_timeout_seconds
        body = ""
        for attempt in range(2):
            try:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError("Writer Provider 调用超过总时限")
                response = await asyncio.wait_for(
                    self._model.ainvoke(messages), timeout=remaining
                )
                total = add_usage(total, message_usage(response))
                body = _strip_code_fence(message_text(response))
                used_numbers = citation_numbers(body)
                unknown = sorted(
                    used_numbers - {int(item["number"]) for item in sources}
                )
                if unknown:
                    raise ValueError(
                        f"引用编号 {unknown} 不在来源列表中"
                    )
                if not is_language_consistent(body, plan.language):
                    raise ValueError("正文语言与研究语言不一致")
                break
            except Exception as exc:
                if attempt == 0:
                    messages = [
                        *messages,
                        HumanMessage(
                            content=(
                                f"上次输出存在问题：{exc}。"
                                "请重新输出完整 Markdown 正文，"
                                "只使用有效来源编号。"
                            )
                        ),
                    ]
                    continue
                fallback, used = self._fallback_markdown(
                    plan, sections, notes_by_section, numbers, termination_reason
                )
                return WriterOutcome(
                    markdown=fallback + self._render_source_section(sources),
                    sources=[item["url"] for item in sources],
                    used_note_ids=used,
                    usage=total,
                    used_fallback=True,
                )
        cited = citation_numbers(body)
        used_note_ids = [
            note.note_id
            for section in sections
            for note in notes_by_section.get(section.task_id, [])
            if numbers.get(note.source_url) in cited
        ]
        markdown = body + self._render_source_section(sources)
        return WriterOutcome(
            markdown=markdown,
            sources=[item["url"] for item in sources],
            used_note_ids=list(dict.fromkeys(used_note_ids)),
            usage=total,
            used_fallback=False,
        )
