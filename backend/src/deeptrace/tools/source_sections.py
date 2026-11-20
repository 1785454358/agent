"""Conservative source structure; coordinates address the unmodified body.

Headings are navigation, never proof of a statement. Unknown layouts keep the
ordinary paragraph fallback; fenced examples and TOC dotted rows are ignored.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class SourceSection:
    start: int
    heading_end: int
    end: int
    title: str
    path: tuple[str, ...]


@lru_cache(maxsize=8)
def source_sections(body: str) -> tuple[SourceSection, ...]:
    fences, opened = [], None
    for match in re.finditer(r"(?m)^[ \t]*(`{3,}|~{3,})[^\n]*", body):
        marker = match.group(1)
        if opened is None:
            opened = (match.start(), marker)
        elif marker[0] == opened[1][0] and len(marker) >= len(opened[1]):
            fences.append((opened[0], match.end()))
            opened = None
    if opened:
        fences.append((opened[0], len(body)))
    headings = []
    patterns = [
        (r"(?m)^(#{1,6})[ \t]+([^\n]{1,160})[ \t]*$", "markdown"),
        (r"(?m)^(\d+(?:\.\d+)*\.)[ \t]*\r?\n([^\n]{1,160})\r?\nSkip to TOC[^\n]*", "extracted"),
        (r"(?m)^(\d+(?:\.\d+)+\.)[ \t]+([A-Z][^\n]{1,150})$", "numbered"),
        (r"(?m)^[ \t]*(?:-[ \t]+)?(?:\*?(?:class|awaitable|coroutine|classmethod|staticmethod)\*?[ \t]+)?"
         r"([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\(([^\n]{0,300})\)[ \t]*¶[ \t]*$", "api"),
    ]
    for pattern, kind in patterns:
        for match in re.finditer(pattern, body):
            if any(a <= match.start() < b for a, b in fences):
                continue
            title = match.group(0).strip() if kind == "api" else match.group(2).strip()
            if re.search(r"\.{3,}|…", title):
                continue
            level = (7 if kind == "api" else len(match.group(1)) if kind == "markdown" else match.group(1).count("."))
            label = title if kind in {"markdown", "api"} else match.group(1) + " " + title
            headings.append((match.start(), match.end(), level, label))
    headings.sort()
    result, parents = [], []
    for i, (start, end, level, title) in enumerate(headings):
        while parents and parents[-1][0] >= level:
            parents.pop()
        path = (*[p[1] for p in parents], title)
        result.append(SourceSection(start, end, headings[i + 1][0] if i + 1 < len(headings) else len(body), title, path))
        parents.append((level, title))
    return tuple(result)


def section_at(body: str, position: int) -> SourceSection | None:
    sections = source_sections(body)
    index = bisect_right([s.start for s in sections], position) - 1
    return sections[index] if index >= 0 else None
