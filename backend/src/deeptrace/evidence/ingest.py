"""把阶段 3 研究笔记转换为可追溯 Evidence。"""

from collections.abc import Mapping, Sequence
import hashlib

from pydantic import BaseModel, Field

from deeptrace.evidence.ids import evidence_id, source_id
from deeptrace.models import Evidence, RawDocument, ResearchNote, Source


class EvidenceIngestResult(BaseModel):
    """一次入库的可序列化结果及诊断信息。"""

    sources: dict[str, Source] = Field(default_factory=dict)
    evidence: dict[str, Evidence] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def locate_quote(content: str, quote: str) -> tuple[int | None, int | None]:
    """返回 quote 在正文中的首次精确字符位置。"""
    start = content.find(quote)
    return (None, None) if start < 0 else (start, start + len(quote))


def _source_from_document(
    document: RawDocument, note: ResearchNote
) -> Source:
    return Source(
        source_id=source_id(document.doc_id),
        doc_id=document.doc_id,
        requested_url=document.requested_url,
        final_url=document.final_url,
        canonical_url=document.canonical_url,
        title=document.title,
        publisher=document.publisher,
        source_kind=note.source_kind,
        publication_date=document.source_published_at,
        modified_date=document.source_modified_at,
        fetched_at=document.fetched_at,
        scraper_used=document.scraper_used,
        content_hash=document.content_hash,
    )


def ingest_notes(
    documents: Mapping[str, RawDocument],
    notes: Sequence[ResearchNote],
    existing_sources: Mapping[str, Source] | None = None,
) -> EvidenceIngestResult:
    """从有效压缩笔记构建 Source 和 Evidence，不接收搜索摘要。"""
    sources = dict(existing_sources or {})
    evidence: dict[str, Evidence] = {}
    warnings: list[str] = []
    accepted_relations = {"in_range", "retrospective", "not_applicable"}

    for note in notes:
        if note.compression_status == "irrelevant":
            continue
        if note.temporal_relation not in accepted_relations:
            continue
        document = documents.get(note.doc_id)
        if document is None:
            warnings.append(
                f"笔记 {note.note_id} 缺少原始文档，未将搜索摘要作为证据"
            )
            continue
        if document.status != "success":
            warnings.append(f"文档 {document.doc_id} 抓取未成功，跳过证据入库")
            continue

        identity = source_id(document.doc_id)
        candidate = _source_from_document(document, note)
        current = sources.get(identity)
        if (
            current is not None
            and current.source_kind != candidate.source_kind
            and current.source_kind != "unknown"
            and candidate.source_kind != "unknown"
        ):
            candidate = candidate.model_copy(update={"source_kind": "unknown"})
            warnings.append(f"文档 {document.doc_id} 的来源类型冲突，已降级为 unknown")
        elif current is not None:
            candidate = current
        sources[identity] = candidate

        for raw_quote in note.evidence_snippets:
            quote = raw_quote.strip()
            if not quote:
                continue
            start, end = locate_quote(document.content, quote)
            location_status = "exact" if start is not None else "unlocated"
            if start is None:
                warnings.append(
                    f"证据摘录未定位：note={note.note_id}, doc={document.doc_id}"
                )
            quote_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
            identity_key = evidence_id(
                identity, note.note_id, quote_hash, start
            )
            evidence[identity_key] = Evidence(
                evidence_id=identity_key,
                source_id=identity,
                doc_id=document.doc_id,
                note_id=note.note_id,
                task_id=note.task_id,
                section_id=note.section_id,
                quote=quote,
                quote_hash=quote_hash,
                char_start=start,
                char_end=end,
                location_status=location_status,
                event_start=note.event_start_date,
                event_end=note.event_end_date,
                temporal_relation=note.temporal_relation,
            )

    return EvidenceIngestResult(
        sources=sources,
        evidence=evidence,
        warnings=warnings,
    )

