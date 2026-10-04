"""Necessary verbatim cores own the budget before optional context."""

from itertools import permutations

import pytest
from deeptrace.domain import EvidenceSupport
from deeptrace.domain.evidence import Evidence
from deeptrace.tools.evidence_views import supported_ranges
from strategies.fixtures import FIXED_NOW


def record():
    return Evidence(
        id="e1",
        canonical_url="https://example.com/budget",
        title="Budget",
        media_type="text/plain",
        content_hash="sha256:test",
        fetched_at=FIXED_NOW,
        source_quality=0.9,
        status="active",
        version=1,
    )


def support(item, body, start, end):
    return EvidenceSupport(
        evidence_id=item.id,
        version=item.version,
        content_hash=item.content_hash,
        start=start,
        end=end,
        quote=body[start:end],
    )


@pytest.mark.parametrize("order", list(permutations([(100, 500), (1000, 1400)])))
def test_all_necessary_cores_fit_before_any_context(order):
    body, item = "_" * 1800, record()
    supports = [support(item, body, *span) for span in order]
    before = [s.model_dump() for s in supports]
    assert supported_ranges(item, body, supports, 800) == [(100, 500), (1000, 1400)]
    assert [s.model_dump() for s in supports] == before


def test_overlap_is_charged_once_then_maximal_context_is_added():
    body, item = "_" * 1800, record()
    supports = [support(item, body, 100, 500), support(item, body, 400, 650)]
    assert supported_ranges(item, body, supports, 700) == [(25, 725)]


def test_adjacency_and_duplicates_do_not_take_extra_budget():
    body, item = "中\n`🧭" * 400, record()
    supports = [support(item, body, 100, 500), support(item, body, 500, 650)]
    assert supported_ranges(item, body, supports + supports[::-1], 550) == [(100, 650)]


def test_boundary_clipping_allows_the_largest_symmetric_margin():
    body, item = "_" * 1000, record()
    assert supported_ranges(item, body, [support(item, body, 0, 20)], 50) == [(0, 50)]


def test_true_overflow_skips_whole_quote_and_tries_later_smaller_quote():
    body, item = "_" * 1800, record()
    supports = [
        support(item, body, *span) for span in [(0, 500), (600, 1100), (1200, 1300)]
    ]
    assert supported_ranges(item, body, supports, 600) == [(0, 500), (1200, 1300)]


@pytest.mark.parametrize("limit", [True, False, 0, -1, 1.0])
def test_limit_is_a_strict_positive_integer(limit):
    with pytest.raises(ValueError, match="positive integer"):
        supported_ranges(record(), "body", [], limit)


@pytest.mark.parametrize(
    "changes",
    [
        {"version": 2},
        {"content_hash": "wrong"},
        {"evidence_id": "other"},
        {"start": True},
        {"start": -1},
        {"end": 501},
        {"quote": "forged"},
        {"start": 0, "end": 501, "quote": "_" * 501},
    ],
)
def test_unvalidated_model_copy_cannot_acquire_budget(changes):
    body, item = "_" * 1000, record()
    invalid = support(item, body, 100, 500).model_copy(update=changes)
    assert supported_ranges(item, body, [invalid], 800) == []


def test_expanding_context_does_not_double_charge_neighbouring_ranges():
    body, item = "_" * 2000, record()
    supports = [support(item, body, 200, 400), support(item, body, 500, 700)]
    assert supported_ranges(item, body, supports, 700) == [(80, 780)]
