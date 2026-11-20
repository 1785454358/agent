"""Bounded text extraction for digitally born research PDFs."""

from io import BytesIO

from pypdf import PdfReader

MAX_PDF_PAGES = 100
MAX_PDF_TEXT_CHARS = 1_000_000
MAX_PAGE_STREAM_BYTES = 8_000_000


class PdfExtractionError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def extract_pdf(data: bytes, *, page_start: int | None = None,
                page_end: int | None = None) -> tuple[str, str]:
    if not data.startswith(b"%PDF-"):
        raise PdfExtractionError("invalid_pdf")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise PdfExtractionError("pdf_encrypted")
        count = len(reader.pages)
        first = 1 if page_start is None else page_start
        last = count if page_end is None else page_end
        if (type(first) is not int or type(last) is not int
                or not 1 <= first <= last <= count):
            raise PdfExtractionError("pdf_invalid_page_range")
        if last - first + 1 > MAX_PDF_PAGES:
            raise PdfExtractionError("pdf_page_limit")
        title = str((reader.metadata or {}).get("/Title") or "").strip()
        sections, total = [], 0
        for number in range(first, last + 1):
            page = reader.pages[number - 1]
            stream = page.get_contents()
            if stream is not None and len(stream.get_data()) > MAX_PAGE_STREAM_BYTES:
                raise PdfExtractionError("pdf_page_stream_limit")
            text = (page.extract_text(extraction_mode="layout") or "").strip()
            # arXiv version/date stamps often run vertically in the margin.
            # Preserve them verbatim, separate from the layout of result tables.
            rotated = (page.extract_text(orientations=(90, 180, 270)) or "").strip()
            if rotated:
                text += "\n\nPDF rotated text (same page):\n" + rotated
            total += len(text)
            if total > MAX_PDF_TEXT_CHARS:
                raise PdfExtractionError("pdf_text_limit")
            if text:
                sections.append(f"## PDF page {number}\n\n{text}")
        if not sections:
            raise PdfExtractionError("pdf_text_unavailable")
        if first != 1 or last != count:
            omitted = ([f"1-{first - 1}"] if first > 1 else []) + ([f"{last + 1}-{count}"] if last < count else [])
            sections.insert(0, f"PDF partial extraction; total pages: {count}; read pages: {first}-{last}; omitted pages: {', '.join(omitted)}. Unread pages were not checked.")
        return title, "\n\n".join(sections)
    except PdfExtractionError:
        raise
    except Exception as exc:
        raise PdfExtractionError("invalid_pdf") from exc
