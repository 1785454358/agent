"""Write one report directly from the flat research context."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from deeptrace.agent._shared import add_usage, message_text, message_usage
from deeptrace.models import TokenUsage
from deeptrace.prompts.writer import build_writer_messages


@dataclass
class WriterOutcome:
    """The generated Markdown, stable source list, and Provider usage."""

    markdown: str
    sources: list[str]
    usage: TokenUsage = field(default_factory=TokenUsage)
    used_fallback: bool = False


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _unique_sources(sources: Sequence[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for source in sources:
        normalized = source.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _append_references(markdown: str, sources: Sequence[str]) -> str:
    body = markdown.rstrip()
    if not sources:
        return body
    references = "\n".join(f"- [{source}]({source})" for source in sources)
    return f"{body}\n\n## References\n\n{references}"


class WriterAgent:
    """Use one bounded Provider call, with one retry, to write a report."""

    def __init__(
        self,
        model: Any,
        *,
        call_timeout_seconds: float = 60.0,
        context_limit_chars: int = 60_000,
    ) -> None:
        if call_timeout_seconds <= 0:
            raise ValueError("Writer 调用超时必须大于 0 秒")
        if context_limit_chars <= 0:
            raise ValueError("Writer 上下文字符上限必须大于 0")
        self._model = model
        self._call_timeout_seconds = call_timeout_seconds
        self._context_limit_chars = context_limit_chars

    @staticmethod
    def _empty_context_markdown(question: str, language: str) -> str:
        if language.lower().startswith("zh"):
            return (
                "# 研究结果\n\n"
                f"研究问题：{question}\n\n"
                "局限：未获得有效资料，无法生成可靠的研究报告。"
            )
        return (
            "# Research Result\n\n"
            f"Research question: {question}\n\n"
            "Limitation: No valid research material was obtained, so a reliable "
            "report cannot be generated."
        )

    @staticmethod
    def _fallback_markdown(
        *,
        question: str,
        context: str,
        language: str,
        termination_reason: str,
    ) -> str:
        if language.lower().startswith("zh"):
            return (
                "# 研究结果\n\n"
                f"研究问题：{question}\n\n"
                "## 局限\n\n"
                "Writer 未能生成完整报告。以下仅展示运行截止前取得的材料，"
                f"终止原因：{termination_reason}。\n\n"
                "## 可用研究材料\n\n"
                f"{context}"
            )
        return (
            "# Research Result\n\n"
            f"Research question: {question}\n\n"
            "## Limitation\n\n"
            "The Writer could not generate a complete report. The material below "
            f"is limited to what was collected before termination: {termination_reason}.\n\n"
            "## Available Research Context\n\n"
            f"{context}"
        )

    async def awrite(
        self,
        *,
        question: str,
        context: str,
        sources: Sequence[str],
        language: str,
        termination_reason: str = "completed",
    ) -> WriterOutcome:
        normalized_sources = _unique_sources(sources)
        normalized_context = context.strip()
        if not normalized_context:
            markdown = self._empty_context_markdown(question, language)
            return WriterOutcome(
                markdown=_append_references(markdown, normalized_sources),
                sources=normalized_sources,
                used_fallback=True,
            )

        bounded_context = normalized_context[: self._context_limit_chars]
        messages = build_writer_messages(
            question=question,
            context=bounded_context,
            language=language,
            termination_reason=termination_reason,
        )
        total = TokenUsage()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._call_timeout_seconds

        for _attempt in range(2):
            try:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError("Writer Provider 调用超过总时限")
                response = await asyncio.wait_for(
                    self._model.ainvoke(messages), timeout=remaining
                )
                total = add_usage(total, message_usage(response))
                body = _strip_code_fence(message_text(response))
                if not body:
                    raise ValueError("Writer 返回了空报告")
                return WriterOutcome(
                    markdown=_append_references(body, normalized_sources),
                    sources=normalized_sources,
                    usage=total,
                    used_fallback=False,
                )
            except Exception:
                continue

        fallback = self._fallback_markdown(
            question=question,
            context=bounded_context,
            language=language,
            termination_reason=termination_reason,
        )
        return WriterOutcome(
            markdown=_append_references(fallback, normalized_sources),
            sources=normalized_sources,
            usage=total,
            used_fallback=True,
        )
