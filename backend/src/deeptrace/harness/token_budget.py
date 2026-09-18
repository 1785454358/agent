"""Token-budgeted context assembly.

The budget is an *allocator and selector*, never a blind truncator:

- pinned segments (instructions, the user question, the output contract) are
  always kept and never cut;
- output tokens are reserved up front so generation always has room to finish;
- elastic segments are added by priority while they fit whole; an elastic
  segment is only shortened when it has a ``min_tokens`` floor and space left,
  otherwise it is dropped as a unit.

This keeps token limits a safety net for pathological inputs instead of an
always-on compressor that degrades answer quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _encoder():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoder().encode(text, disallowed_special=()))


def truncate_to_tokens(text: str, limit: int) -> str:
    if limit <= 0 or not text:
        return ""
    encoder = _encoder()
    tokens = encoder.encode(text, disallowed_special=())
    if len(tokens) <= limit:
        return text
    return encoder.decode(tokens[:limit])


class SegmentPriority(StrEnum):
    PINNED = "pinned"
    HIGH = "high"
    NORMAL = "normal"


@dataclass(frozen=True)
class Segment:
    """One addressable block of context.

    ``text`` carries its own separators so callers keep exact formatting.
    ``min_tokens`` lets an elastic segment survive partially instead of being
    dropped, but only down to a floor that stays useful.
    """

    name: str
    text: str
    priority: SegmentPriority = SegmentPriority.NORMAL
    min_tokens: int = 0


@dataclass(frozen=True)
class TokenBudgetConfig:
    """Static budget for one model call."""

    context_tokens: int = 128_000
    output_reserve_tokens: int = 4_096
    safety_tokens: int = 2_048

    @property
    def input_budget(self) -> int:
        return max(
            0,
            self.context_tokens - self.output_reserve_tokens - self.safety_tokens,
        )


@dataclass
class BudgetAllocation:
    context_tokens: int
    output_reserve: int
    input_budget: int
    used_tokens: int
    included: dict[str, int]
    dropped: list[str]
    truncated: list[str]
    pinned_overflow: bool
    bound: bool

    def summary(self) -> dict[str, object]:
        return {
            "context_tokens": self.context_tokens,
            "output_reserve": self.output_reserve,
            "input_budget": self.input_budget,
            "used_tokens": self.used_tokens,
            "dropped": list(self.dropped),
            "truncated": list(self.truncated),
            "pinned_overflow": self.pinned_overflow,
            "bound": self.bound,
        }


def assemble_with_budget(
    segments: list[Segment], config: TokenBudgetConfig
) -> tuple[str, BudgetAllocation]:
    """Return (assembled_text, allocation); never mutates the segments."""
    budget = config.input_budget
    sizes = [count_tokens(segment.text) for segment in segments]
    render: list[str | None] = [None] * len(segments)
    dropped: list[str] = []
    truncated: list[str] = []
    remaining = budget

    # Pinned segments always go in, even if that overflows the budget: losing
    # the instructions or the output contract is worse than overshooting.
    for index, segment in enumerate(segments):
        if segment.priority is SegmentPriority.PINNED:
            render[index] = segment.text
            remaining -= sizes[index]
    pinned_overflow = remaining < 0
    if remaining < 0:
        remaining = 0

    for priority in (SegmentPriority.HIGH, SegmentPriority.NORMAL):
        for index, segment in enumerate(segments):
            if render[index] is not None or segment.priority is not priority:
                continue
            need = sizes[index]
            if need <= remaining:
                render[index] = segment.text
                remaining -= need
            elif segment.min_tokens > 0 and remaining >= segment.min_tokens:
                piece = truncate_to_tokens(segment.text, remaining)
                render[index] = piece
                remaining -= count_tokens(piece)
                truncated.append(segment.name)
            else:
                dropped.append(segment.name)

    text = "".join(part for part in render if part is not None)
    included = {
        segment.name: count_tokens(render[index])
        for index, segment in enumerate(segments)
        if render[index] is not None
    }
    bound = bool(dropped or truncated or pinned_overflow)
    allocation = BudgetAllocation(
        context_tokens=config.context_tokens,
        output_reserve=config.output_reserve_tokens,
        input_budget=budget,
        used_tokens=count_tokens(text),
        included=included,
        dropped=dropped,
        truncated=truncated,
        pinned_overflow=pinned_overflow,
        bound=bound,
    )
    return text, allocation
