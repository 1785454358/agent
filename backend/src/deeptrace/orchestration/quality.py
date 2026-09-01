"""阶段 3 笔记时间与来源质量汇总。"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from tld import get_fld

from deeptrace.models import ResearchNote

QUALIFIED_SOURCE_KINDS = {"official", "academic", "reputable_secondary"}


def note_is_valid(note: ResearchNote) -> bool:
    return note.compression_status != "irrelevant" and note.temporal_relation in {
        "in_range", "retrospective", "not_applicable"
    }


def source_identity(url: str) -> str:
    return get_fld(url, fail_silently=True) or (urlsplit(url).hostname or url)


@dataclass(frozen=True, slots=True)
class NoteQualitySummary:
    valid_ids: list[str]
    retrospective_ids: list[str]
    unknown_ids: list[str]
    out_of_range_ids: list[str]
    qualified_urls: list[str]
    source_identities: set[str]
    has_qualified_kind: bool


def summarize_note_quality(notes: list[ResearchNote]) -> NoteQualitySummary:
    valid = [note for note in notes if note_is_valid(note)]
    qualified = [note for note in valid if note.source_kind in QUALIFIED_SOURCE_KINDS]
    urls = list(dict.fromkeys(note.source_url for note in valid))
    return NoteQualitySummary(
        valid_ids=[note.note_id for note in valid],
        retrospective_ids=[note.note_id for note in valid if note.temporal_relation == "retrospective"],
        unknown_ids=[note.note_id for note in notes if note.temporal_relation == "unknown"],
        out_of_range_ids=[note.note_id for note in notes if note.temporal_relation == "out_of_range"],
        qualified_urls=urls,
        source_identities={source_identity(url) for url in urls},
        has_qualified_kind=bool(qualified),
    )
