"""Same-length view hiding Markdown code from citation processing."""

import re

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)")
_INLINE = re.compile(r"(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)", re.DOTALL)


def without_code(text: str) -> str:
    """Mask code while retaining offsets for replacements in the original text."""
    masked = list(text)
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        match = _FENCE.match(line)
        protected = fence is not None
        if fence is not None:
            if (
                match
                and match[1][0] == fence[0]
                and len(match[1]) >= len(fence)
                and not match[2].strip()
            ):
                fence = None
        elif match and not (match[1][0] == "`" and "`" in match[2]):
            fence = match[1]
            protected = True
        if protected:
            masked[offset : offset + len(line)] = " " * len(line)
        offset += len(line)
    view = "".join(masked)
    for match in _INLINE.finditer(view):
        masked[match.start() : match.end()] = " " * (match.end() - match.start())
    return "".join(masked)
