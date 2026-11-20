"""Bound futile acquisition retries by observed URL/version/format and failure."""

from collections import Counter

PERMANENT_FAILURES = frozenset({"response_too_large", "document_text_limit", "pdf_page_limit", "pdf_text_limit",
    "pdf_page_stream_limit", "pdf_encrypted", "invalid_pdf", "pdf_text_unavailable",
    "unsupported_content_type", "unsafe_url"})


def blocked_acquisitions(state):
    result = dict(state.get("blocked_acquisitions") or {})
    counts = Counter()
    for outcome in [*(state.get("topic_outcomes") or []), *(state.get("researcher_outcomes") or [])]:
        for error in outcome.errors:
            if error.stage != "fetch" or not error.target:
                continue
            key = (error.target, error.code)
            counts[key] += 1
            if error.code in PERMANENT_FAILURES or counts[key] >= 2:
                result[error.target] = error.code
    return dict(list(result.items())[-100:])
