"""The tool and response boundaries share verbatim source selection."""

import importlib
import importlib.util


def test_tail_selector_is_shared_with_response_without_rewriting_body():
    assert importlib.util.find_spec("deeptrace.tools.evidence_views") is not None
    select = importlib.import_module(
        "deeptrace.tools.evidence_views"
    ).select_source_excerpt
    legacy = importlib.import_module(
        "deeptrace.responses.excerpts"
    ).select_source_excerpt
    body = "Unrelated paragraph.\n\n" * 700 + "Store persists cross-thread facts."
    excerpt = select(body, "Store cross-thread facts", 2000)
    assert legacy is select
    assert "Store persists cross-thread facts." in excerpt.text
    assert len(excerpt.text) <= 2000
    assert all(body[r.start : r.end] in excerpt.text for r in excerpt.ranges)
