from deeptrace.writer import render_report

SOURCES = [
    "https://example.com/a",
    "https://example.com/b",
    "https://example.com/c",
]


def test_renderer_numbers_citations_by_first_appearance() -> None:
    report = render_report(
        "# 报告\n\n## 市场\n\nB [[source:2]]，A [[source:1]]，B [[source:2]]。",
        SOURCES,
        "zh-CN",
    )

    assert report == (
        "报告\n\n市场\n\nB [1]，A [2]，B [1]。\n\n"
        "参考内容\n\n"
        "[1] https://example.com/b\n"
        "[2] https://example.com/a"
    )


def test_renderer_converts_links_and_urls_without_leaking_body_urls() -> None:
    report = render_report(
        "1 发现\n\n[来源乙](https://example.com/b) 与 "
        "https://example.com/a；未知 [页面](https://unknown.example/x)。",
        SOURCES,
        "zh-CN",
    )
    body, references = report.split("\n\n参考内容\n\n", maxsplit=1)

    assert "http" not in body
    assert body == "1 发现\n\n来源乙 [1] 与 [2]；未知 页面。"
    assert references == "[1] https://example.com/b\n[2] https://example.com/a"


def test_renderer_replaces_model_number_with_source_then_renumbers() -> None:
    report = render_report(
        "1 Result\n\nThird source [3], then first source [1].",
        SOURCES,
        "en",
    )

    assert report.endswith(
        "References\n\n"
        "[1] https://example.com/c\n"
        "[2] https://example.com/a"
    )


def test_renderer_discards_model_reference_section_and_uncited_sources() -> None:
    report = render_report(
        "# Title\n\n## 1 Finding\n\nClaim [[source:1]].\n\n"
        "## References\n\n- https://example.com/b",
        SOURCES,
        "en",
    )

    assert report == (
        "Title\n\n1 Finding\n\nClaim [1].\n\n"
        "References\n\n[1] https://example.com/a"
    )
    assert "example.com/b" not in report


def test_renderer_strips_bare_heading_marker_line() -> None:
    report = render_report(
        "1 Finding\n\nClaim [[source:1]].\n\n###\n\n2 Next\n\nMore [[source:2]]。",
        SOURCES,
        "zh-CN",
    )

    body, _references = report.split("\n\n参考内容\n\n", maxsplit=1)

    assert "#" not in body
    assert "1 Finding" in body
    assert "2 Next" in body


def test_renderer_replaces_model_reference_content_section() -> None:
    report = render_report(
        "报告\n\n1 总述\n\n结论 [[source:1]]。\n\n"
        "参考内容\n\n[1] 模型自行输出的来源",
        SOURCES,
        "zh-CN",
    )

    assert report == (
        "报告\n\n1 总述\n\n结论 [1]。\n\n"
        "参考内容\n\n[1] https://example.com/a"
    )
