"""Catch entity starvation, partial identifier matches and false prefix reads."""

import pytest

from deeptrace.tools.evidence_views import select_source_excerpt


def selected(body, excerpt):
    return "\n".join(body[r.start : r.end] for r in excerpt.ranges)


def test_target_entities_are_not_displaced_by_generic_task_words():
    distractor = "任务异常取消行为对比说明：任务的异常处理与取消行为需要考虑任务执行。"
    body = (distractor + "\n\n") * 80 + (
        "## pkg.OpenGroup\n\nOpenGroup stops siblings on failure.\n\n"
        "## pkg.collect\n\ncollect leaves siblings running.\n\n"
    )
    excerpt = select_source_excerpt(
        body, "对比pkg.OpenGroup与pkg.collect的任务异常取消行为", 650
    )
    text = selected(body, excerpt)
    assert "OpenGroup stops siblings on failure." in text
    assert "collect leaves siblings running." in text
    assert "## pkg.OpenGroup" in text
    assert "## pkg.collect" in text


def test_identifier_prefix_is_not_a_target_match():
    body = (
        "RunNodeSuffix timeout retry error task cancellation.\n\n" * 80
        + "RunNode keeps the original operation.\n\n"
    )
    excerpt = select_source_excerpt(body, "pkg.RunNode timeout retry error task", 230)
    assert "RunNode keeps the original operation." in selected(body, excerpt)
    assert "RunNodeSuffix" not in selected(body, excerpt)


def test_adjacent_exception_condition_is_not_lost_after_api_heading():
    body = (
        "Background discussion.\n\n" * 150 + "## pkg.open_pool\n\n"
        "open_pool cancels the pending operations.\n\n"
        "If cleanup fails, the errors are grouped instead of discarded.\n\n"
        "## Other API\n\nUnrelated trailing notes.\n\n" * 1
    )
    excerpt = select_source_excerpt(body, "pkg.open_pool cancellation", 600)
    assert "open_pool cancels the pending operations." in selected(body, excerpt)
    assert "If cleanup fails, the errors are grouped instead of discarded." in selected(
        body, excerpt
    )
    assert "Unrelated trailing notes." not in selected(body, excerpt)


def test_query_does_not_return_unrelated_prefix():
    result = select_source_excerpt("Ordinary background.\n\n" * 100, "quasar", 600)
    assert result.ranges == ()
    assert result.strategy == "no_match"


def test_matching_indivisible_block_is_omitted_not_sliced():
    result = select_source_excerpt("x" * 12000 + " ZetaGuard", "ZetaGuard", 600)
    assert result.ranges == ()
    assert result.strategy == "budget_omitted"


@pytest.mark.parametrize(
    "fact,query",
    [
        ("许可证禁止跨租户转售。", "许可证转售"),
        ("The license forbids resale across tenants.", "license resale"),
    ],
)
def test_natural_language_queries_still_select_actual_paragraphs(fact, query):
    body = "Ordinary background.\n\n" * 200 + fact + "\n\n"
    result = select_source_excerpt(body, query, 600)
    assert fact in selected(body, result)
    assert len(result.text) <= 600
    assert all(body[r.start : r.end] in result.text for r in result.ranges)


def test_short_document_is_delivered_full_without_claiming_keyword_selection():
    result = select_source_excerpt("Unrelated short document.", "quasar", 600)
    assert result.text == "Unrelated short document."
    assert result.strategy == "full"


def test_unqueried_short_document_remains_explicit_full_read():
    assert select_source_excerpt("Short document.", "", 600).text == "Short document."


def test_actual_api_section_beats_incidental_mention_in_another_section():
    body = (
        "## pkg.OpenGroup\n\n"
        "A group of concurrent operations.\n\n"
        "When an operation fails, remaining operations are cancelled.\n\n"
        "The errors are grouped after cleanup.\n\n"
        "## pkg.OtherNode\n\n"
        "OpenGroup task exception cancellation retry result comparison. "
        * 1
        + "task exception cancellation retry result comparison. " * 4
        + "\n\n"
        + "Unrelated background.\n\n" * 100
    )
    result = select_source_excerpt(
        body, "pkg.OpenGroup task exception cancellation retry result comparison", 420
    )
    text = selected(body, result)
    assert "remaining operations are cancelled." in text
    assert "The errors are grouped after cleanup." in text
    assert "## pkg.OtherNode" not in text


def test_blank_lines_and_hash_comments_inside_code_do_not_create_headings():
    body = (
        "## pkg.open_pool\n\n"
        "open_pool performs cleanup.\n\n"
        "```python\nfirst()\n\n# not a heading\nsecond()\n```\n\n"
        "An exception is re-raised after cleanup.\n\n"
        + "Unrelated background.\n\n"
        * 100
    )
    result = select_source_excerpt(body, "pkg.open_pool exception cleanup", 700)
    text = selected(body, result)
    assert "An exception is re-raised after cleanup." in text
    for span in result.ranges:
        assert body[span.start : span.end].count("```") % 2 == 0


def test_flattened_long_hash_comment_does_not_reset_api_section():
    body = (
        "## pkg.open_pool\n\nopen_pool starts operations.\n\n"
        + "# output comment "
        + "irrelevant sample values " * 20
        + "\n\n"
        + "On failure, all remaining operations are cancelled.\n\n"
        + "Unrelated notes.\n\n" * 100
    )
    result = select_source_excerpt(body, "pkg.open_pool failure cancellation", 900)
    assert "all remaining operations are cancelled." in selected(body, result)
