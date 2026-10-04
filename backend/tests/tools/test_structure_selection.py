"""Catch mid-paragraph cuts and starvation of independently supplied facts."""

import pytest

from deeptrace.tools.evidence_views import select_source_excerpt


def competition_body():
    alpha = (
        "Alpha aperture voltage amperage circuitry reliability density thermal drift. "
    )
    return (alpha * 8 + "\n\n") * 12 + "Beta lease does not permit redistribution.\n\n"


def test_complete_paragraph_is_not_expanded_into_cut_neighbours():
    fact = "Zeta licenses do not permit commercial reuse under version 2."
    body = (
        "Ordinary background.\n\n" * 300 + fact + "\n\n" + "Unrelated notes.\n\n" * 300
    )
    excerpt = select_source_excerpt(body, "Zeta licenses", 600)
    assert fact in excerpt.text
    for span in excerpt.ranges:
        assert span.start == 0 or body[span.start - 2 : span.start] == "\n\n"
        assert span.end == len(body) or body[span.end - 2 : span.end] == "\n\n"
    assert len(excerpt.text) <= 600


@pytest.mark.parametrize(
    "fact,query",
    [
        ("Zeta does not replay external writes under version 2.", "Zeta replay"),
        ("版本二的泽塔恢复不能重放外部写入。", "泽塔恢复写入"),
    ],
)
def test_long_paragraph_keeps_complete_sentence_boundaries(fact, query):
    body = (
        "An ordinary background sentence. " * 90
        + fact
        + " "
        + "A trailing sentence. " * 90
    )
    excerpt = select_source_excerpt(body, query, 1500)
    assert fact in excerpt.text
    for span in excerpt.ranges:
        assert body[span.start : span.end].rstrip().endswith((".", "。"))
        assert span.start == 0 or body[: span.start].rstrip().endswith((".", "。"))


def test_long_line_based_block_keeps_complete_rows():
    fact = "ZETA_LIMIT = 'no external writes in version 2'\n"
    body = "ordinary = 1\n" * 100 + fact + "ordinary = 2\n" * 100
    excerpt = select_source_excerpt(body, "ZETA_LIMIT", 1500)
    assert fact in excerpt.text
    assert all(r.start == 0 or body[r.start - 1] == "\n" for r in excerpt.ranges)
    assert all(r.end == len(body) or body[r.end - 1] == "\n" for r in excerpt.ranges)


def test_independent_focus_fact_is_not_starved_by_original_question():
    body = competition_body()
    excerpt = select_source_excerpt(
        body,
        "Alpha aperture voltage amperage circuitry reliability density thermal drift",
        3000,
        focus_queries=[
            "Alpha aperture voltage amperage circuitry reliability density thermal drift",
            "Beta lease",
        ],
    )
    assert (
        "Alpha aperture voltage amperage circuitry reliability density thermal drift."
        in excerpt.text
    )
    assert "Beta lease does not permit redistribution." in excerpt.text
    assert len(excerpt.text) <= 3000


def test_repeated_focus_reuses_selected_range_without_losing_other_fact():
    body = competition_body()
    excerpt = select_source_excerpt(
        body,
        "Alpha aperture",
        3000,
        focus_queries=["Alpha aperture", "Alpha aperture", "Beta lease"],
    )
    assert "Beta lease does not permit redistribution." in excerpt.text
    assert len({(r.start, r.end) for r in excerpt.ranges}) == len(excerpt.ranges)
    assert all(a.end < b.start for a, b in zip(excerpt.ranges, excerpt.ranges[1:]))


@pytest.mark.parametrize("limit", [1, 40, 150, 600, 3000])
def test_focus_selection_preserves_coordinates_within_rendered_budget(limit):
    body = (
        "背景🙂无关。\n\n" * 1000 + "泽塔不能跨租户共享。\n\nBeta lease forbids resale."
    )
    excerpt = select_source_excerpt(
        body, "泽塔共享", limit, focus_queries=["泽塔共享", "Beta lease"]
    )
    assert len(excerpt.text) <= limit
    assert (
        select_source_excerpt(
            body, "泽塔共享", limit, focus_queries=["泽塔共享", "Beta lease"]
        )
        == excerpt
    )
    for span in excerpt.ranges:
        assert body[span.start : span.end] in excerpt.text
        assert span.start_line == body.count("\n", 0, span.start) + 1
        assert span.end_line == body.count("\n", 0, span.end - 1) + 1


def test_short_source_still_returns_exact_body_with_focus():
    body = "Beta\n\nBeta lease forbids resale.🙂"
    assert (
        select_source_excerpt(body, "Alpha", 3000, focus_queries=["Beta"]).text == body
    )


def test_unbreakable_long_text_reports_budget_omission_without_partial_sentence():
    fact = "Zeta does not replay external writes."
    body = "x" * 12000 + fact
    excerpt = select_source_excerpt(body, "Zeta replay writes", 3000)
    assert excerpt.ranges == ()
    assert excerpt.strategy == "budget_omitted"
    assert len(excerpt.text) <= 3000
    assert excerpt.omitted_ranges


def test_no_match_does_not_read_an_unrelated_prefix():
    excerpt = select_source_excerpt("ordinary text " * 1000, "quasar", 600)
    assert excerpt.strategy == "no_match"
    assert excerpt.ranges == ()
    assert "quasar" not in excerpt.text
    assert len(excerpt.text) <= 600


@pytest.mark.parametrize("limit", [0, -1, True, 1.2])
def test_invalid_original_budget_still_rejected(limit):
    with pytest.raises(ValueError):
        select_source_excerpt("fact", "fact", limit)
