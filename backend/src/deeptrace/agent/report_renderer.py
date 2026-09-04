"""Deterministically format flat Writer output for final presentation."""

from __future__ import annotations

from collections.abc import Sequence
import re


_ATX_HEADING = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+")
_REFERENCE_SECTION = re.compile(
    r"(?ims)^\s*#{0,6}\s*(?:参考文献|references)\s*$.*\Z"
)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_MODEL_NUMBER = re.compile(r"\[(\d+)\]")
_SOURCE_MARKER = re.compile(r"\[\[source:(\d+)\]\]", re.IGNORECASE)
_BARE_URL = re.compile(r"https?://[^\s<>\])，。；、]+")


def _replace_source_references(markdown: str, sources: Sequence[str]) -> str:
    source_ids = {source: index for index, source in enumerate(sources, start=1)}

    def replace_link(match: re.Match[str]) -> str:
        label, url = match.groups()
        source_id = source_ids.get(url)
        if source_id is None:
            return label
        return f"{label} [[source:{source_id}]]"

    body = _MARKDOWN_LINK.sub(replace_link, markdown)
    body = _MODEL_NUMBER.sub(
        lambda match: (
            f"[[source:{match.group(1)}]]"
            if 1 <= int(match.group(1)) <= len(sources)
            else ""
        ),
        body,
    )
    for source in sorted(sources, key=len, reverse=True):
        body = body.replace(source, f"[[source:{source_ids[source]}]]")
    return _BARE_URL.sub("", body)


def render_report(markdown: str, sources: Sequence[str], language: str) -> str:
    """Render citations by first appearance and append cited source URLs."""
    body = _REFERENCE_SECTION.sub("", markdown.strip()).rstrip()
    body = _ATX_HEADING.sub("", body)
    body = _replace_source_references(body, sources)
    citation_numbers: dict[int, int] = {}
    cited_sources: list[str] = []

    def replace_marker(match: re.Match[str]) -> str:
        source_id = int(match.group(1))
        if not 1 <= source_id <= len(sources):
            return ""
        if source_id not in citation_numbers:
            citation_numbers[source_id] = len(cited_sources) + 1
            cited_sources.append(sources[source_id - 1])
        return f"[{citation_numbers[source_id]}]"

    body = _SOURCE_MARKER.sub(replace_marker, body).rstrip()
    if not cited_sources:
        return body
    heading = "参考文献" if language.lower().startswith("zh") else "References"
    references = "\n".join(
        f"[{index}] {source}"
        for index, source in enumerate(cited_sources, start=1)
    )
    return f"{body}\n\n{heading}\n\n{references}"
