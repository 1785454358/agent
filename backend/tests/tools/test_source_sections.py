"""Section ownership must survive bounded verbatim retrieval."""

from deeptrace.tools.evidence_views import select_source_excerpt


def test_flattened_numbered_heading_travels_with_its_503_rule():
    body = (
        "15.5.14.\n413 Content Too Large\nSkip to TOC\n"
        "If the condition is temporary, the server SHOULD generate Retry-After.\n¶\n"
        + "Unrelated detail. " * 100
        + "\n15.6.4.\n503 Service Unavailable\nSkip to TOC\n"
        "The 503 status code indicates temporary overload. The server MAY send Retry-After.\n¶\n"
        "15.6.5.\n504 Gateway Timeout\nSkip to TOC\nOther rule."
    )
    excerpt = select_source_excerpt(body, "503 Retry-After", 450)
    assert "503 Service Unavailable" in excerpt.text
    assert "The server MAY send Retry-After" in excerpt.text
    for span in excerpt.ranges:
        if "The 503 status" in body[span.start:span.end]:
            assert "503 Service Unavailable" in body[span.start:span.end]
    assert len(excerpt.text) <= 450


def test_markdown_rule_keeps_title_without_needing_a_code_identifier():
    body = "# Archive policy\n\n" + "unrelated. " * 100
    body += "\n\n## Retention\n\nRecords MUST be kept for seven years.\n\n## Removal\n\nOther rule."
    excerpt = select_source_excerpt(body, "Records seven years", 200)
    assert "## Retention" in excerpt.text
    assert "Records MUST be kept for seven years" in excerpt.text


def test_matching_short_section_is_read_with_conditions_and_exceptions():
    body = "Background. " * 200 + "\n\n## Retention\n\nRecords must remain.\n\n"
    body += "This applies only after approval.\n\nAn exception requires a signed release.\n\n## Removal\n\nOther."
    excerpt = select_source_excerpt(body, "Retention", 350)
    assert "This applies only after approval" in excerpt.text
    assert "An exception requires a signed release" in excerpt.text
    assert len(excerpt.text) <= 350


def test_section_context_never_expands_an_authorized_read_range():
    body = "## Private heading\n\nPublic clause with retention period.\n\n" + "Other. " * 100
    start = body.index("Public clause")
    excerpt = select_source_excerpt(body, "retention", 120, eligible_ranges=[(start, start + 42)])
    assert all(start <= r.start and r.end <= start + 42 for r in excerpt.ranges)
    assert "Private heading" not in excerpt.text


def test_fenced_example_titles_do_not_change_real_section_ownership():
    from deeptrace.tools.source_sections import section_at
    body = "## Retention\n\n```text\n# Not a real heading\n```\nRecords MUST remain.\n"
    owner = section_at(body, body.index("Records"))
    assert owner.title == "Retention"


def test_extracted_api_signature_owns_its_conditions_until_the_next_method():
    from deeptrace.tools.source_sections import section_at
    body = "## Concurrent tasks\n\n- \n*awaitable* asyncio.gather(**aws*, *return_exceptions=False*)¶\n"
    body += "- The first exception is propagated.\n\nOther awaitables will not be cancelled.\n\n"
    body += "cancel(*msg=None*)¶\nRequest cooperative cancellation.\n"
    assert "asyncio.gather" in section_at(body, body.index('Other awaitables')).title
    assert section_at(body, body.index('Request cooperative')).title.startswith('cancel(')


def test_supported_quote_reserves_its_heading_before_optional_context():
    from deeptrace.domain import EvidenceSupport
    from deeptrace.tools.evidence_views import select_supported_passages
    from deeptrace.domain.evidence import Evidence
    from datetime import UTC, datetime

    body = "## Retention\n\n" + "Scope note. " * 30 + "\n\nRecords MUST remain.\n\n" + "other. " * 100
    start = body.index("Records")
    record = Evidence(id="evidence-example", canonical_url="https://example.com/rule", title="Rule",
        content_hash="sha256:example", version=1, fetched_at=datetime.now(UTC), media_type="text/plain",
        source_quality=0.9, status="active")
    support = EvidenceSupport(evidence_id=record.id, version=1, content_hash=record.content_hash,
        start=start, end=start + 20, quote=body[start:start+20])
    passages = select_supported_passages(record, body, [support], question="Records", limit=100)
    assert any("## Retention" in p.text for p in passages)
    assert any(support.quote in p.text for p in passages)
    assert sum(len(p.text) for p in passages) <= 100
