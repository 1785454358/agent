"""Prompt construction for reports written from flat source context."""

from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


WRITER_SYSTEM_PROMPT = (
    "You are DeepTrace Report Writer. Write a complete Markdown research report "
    "using only the supplied research context. Cite supporting material with inline "
    "Markdown links, and use only URLs that appear in a Source field. Do not invent "
    "facts or sources, and do not create a References section. State material "
    "limitations plainly. Return only the Markdown report body."
)


def build_writer_messages(
    *,
    question: str,
    context: str,
    language: str,
    termination_reason: str,
) -> list[BaseMessage]:
    """Put the question and direct Source/Title/Content text in one user message."""
    user_content = (
        f"Research question:\n{question.strip()}\n\n"
        f"Report language:\n{language}\n\n"
        f"Run termination reason:\n{termination_reason}\n\n"
        "Research context:\n"
        f"{context.strip()}"
    )
    return [
        SystemMessage(content=WRITER_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]
