from deeptrace.evidence import ingest_notes


def test_ingest_locates_exact_quote(raw_document, research_note) -> None:
    note = research_note.model_copy(
        update={"evidence_snippets": ["整页正文唯一标记"]}
    )

    result = ingest_notes({raw_document.doc_id: raw_document}, [note])

    item = next(iter(result.evidence.values()))
    assert item.location_status == "exact"
    assert item.char_start is not None
    assert item.char_end is not None
    assert raw_document.content[item.char_start:item.char_end] == item.quote


def test_unmatched_quote_is_diagnostic_only(raw_document, research_note) -> None:
    note = research_note.model_copy(update={"evidence_snippets": ["并不存在"]})

    result = ingest_notes({raw_document.doc_id: raw_document}, [note])

    assert next(iter(result.evidence.values())).location_status == "unlocated"
    assert any("未定位" in warning for warning in result.warnings)


def test_source_kind_conflict_downgrades_to_unknown(
    raw_document, research_note
) -> None:
    official = research_note.model_copy(
        update={
            "note_id": "note-official",
            "source_kind": "official",
            "evidence_snippets": ["整页正文唯一标记"],
        }
    )
    secondary = research_note.model_copy(
        update={
            "note_id": "note-secondary",
            "source_kind": "reputable_secondary",
            "evidence_snippets": ["整页正文唯一标记"],
        }
    )

    result = ingest_notes(
        {raw_document.doc_id: raw_document}, [official, secondary]
    )

    assert next(iter(result.sources.values())).source_kind == "unknown"
    assert any("来源类型冲突" in warning for warning in result.warnings)


def test_ingest_rejects_invalid_notes_and_missing_documents(
    raw_document, research_note
) -> None:
    irrelevant = research_note.model_copy(
        update={"compression_status": "irrelevant"}
    )
    out_of_range = research_note.model_copy(
        update={"note_id": "note-out", "temporal_relation": "out_of_range"}
    )
    tavily_only = research_note.model_copy(
        update={"note_id": "note-search", "doc_id": "search-result"}
    )

    result = ingest_notes(
        {raw_document.doc_id: raw_document},
        [irrelevant, out_of_range, tavily_only],
    )

    assert result.evidence == {}
    assert any("缺少原始文档" in warning for warning in result.warnings)

