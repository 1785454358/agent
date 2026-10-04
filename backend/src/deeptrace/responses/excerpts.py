"""Compatibility import for existing response and evaluation consumers."""

from deeptrace.tools.evidence_views import (
    SourceExcerpt,
    SourceRange,
    select_source_excerpt,
)

__all__ = ["SourceExcerpt", "SourceRange", "select_source_excerpt"]
