"""Recognize full publication/submission dates in visible original text."""

import re
from datetime import UTC, date, datetime

_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_MONTH = "(?:" + "|".join([*_MONTHS, *(month[:3] for month in _MONTHS)]) + ")"
_DATES = re.compile(
    rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}\s+{_MONTH}\s+\d{{4}}|{_MONTH}\s+\d{{1,2}},?\s+\d{{4}})\b"
    r"|\d{4}年\d{1,2}月\d{1,2}日",
    re.IGNORECASE,
)
_LABEL = re.compile(
    r"\b(?:published|publication|posted|submitted|first online|released|received|accepted|copyright|updated|modified)\b"
    r"|\barxiv:\s*\d{4}\.\d{4,5}(?:v\d+)?|发表|发布|公开|©",
    re.IGNORECASE,
)


def is_declared_review(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:this|our)\s+(?:perspective|review)\s+(?:article|paper)\b",
            text,
            re.IGNORECASE,
        )
    )


def source_is_news(text: str) -> bool:
    return bool(re.search(r"^Source type \(HTML metadata\): NewsArticle\s*$", text, re.MULTILINE))


def visible_publication_dates(text: str, *, source_is_news_page: bool = False) -> set[date]:
    dates = set()
    news = source_is_news_page or source_is_news(text)
    for match in _DATES.finditer(text):
        before = text[max(0, match.start() - 70) : match.start()]
        if news and not re.search(r"journal reference|original (?:paper|publication)|paper (?:was )?published|论文发表", before, re.IGNORECASE):
            # A news item's own Published header is not an original-paper date.
            continue
        # Received/accepted and footer years are not publication evidence.
        labels = list(_LABEL.finditer(before))
        if not labels or re.fullmatch(
            r"received|accepted|copyright|updated|modified|©",
            labels[-1].group(),
            re.IGNORECASE,
        ):
            continue
        value = match.group().replace(",", "")
        for fmt in (
            "%Y-%m-%d",
            "%d %B %Y",
            "%B %d %Y",
            "%d %b %Y",
            "%b %d %Y",
            "%Y年%m月%d日",
        ):
            try:
                dates.add(
                    datetime.strptime(value.title(), fmt).replace(tzinfo=UTC).date()
                )
                break
            except ValueError:
                pass
    return dates
