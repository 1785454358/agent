"""Bounded discovery from explicit links in authorized, active parent evidence."""

import logging
import re
from urllib.parse import urlsplit

from deeptrace.domain import EvidenceLifecycleStatus
from deeptrace.harness.agent_tools import _urls_from_body
from deeptrace.tools.evidence_views import _matches, _terms


def reference_index_links(task, record, body, seen_urls):
    """Follow actual API-index anchors, never treat an index as the reference."""
    from deeptrace.tools.scraper.document_formats import FORMATS_LABEL

    if FORMATS_LABEL in body:
        links = body.rsplit(FORMATS_LABEL, 1)[1].splitlines()[1:7]
        formats = [u.strip() for u in links if u.strip() in seen_urls
                   and urlsplit(u.strip()).hostname == urlsplit(record.canonical_url).hostname
                   and urlsplit(u.strip()).path.lower().endswith((".txt", ".html"))]
        if formats:
            return sorted(formats, key=lambda u: not urlsplit(u).path.lower().endswith(".txt"))[:1]
    if not re.search(r"\bindex\b|索引", record.title, re.I) and not re.search(
        r"(?:api-index|index-files)/?", urlsplit(record.canonical_url).path, re.I
    ):
        return []
    terms = _terms(" ".join([task.query, *task.search_queries]))
    host = urlsplit(record.canonical_url).netloc
    candidates = []
    for url in _urls_from_body(body, limit=200):
        # Reference navigation stays on the observed documentation host.
        if url == record.canonical_url or url not in seen_urls or urlsplit(url).netloc != host:
            continue
        line = next((line for line in body.splitlines() if url in line), "")[:2000]
        score = sum(_matches(line.casefold(), term) for term in terms)
        if score:
            candidates.append((score, url))
    return [url for _, url in sorted(candidates, key=lambda item: -item[0])[:2]]


async def source_link_candidates(task, context):
    """Links are navigation hints, not facts or permission to leave a corpus."""
    if context.source_evidence_ids is not None or task.source_policy == "research_results":
        return []
    terms = _terms(" ".join([task.query, *task.search_queries, *[
        r.description for r in task.requirements
        if not task.target_requirement_ids or r.id in task.target_requirement_ids
    ]]))
    candidates = {}
    for identity in task.authorized_evidence_ids[:32]:
        try:
            record = await context.evidence_store.get(context.workspace_id, identity)
            if record.status is not EvidenceLifecycleStatus.ACTIVE:
                continue
            body = await context.evidence_store.read_body(context.workspace_id, identity)
        except Exception:  # Optional navigation must not discard search results; cancellation propagates.
            logging.getLogger(__name__).warning("Source navigation unavailable", exc_info=True)
            continue
        for url in _urls_from_body(body, limit=200):
            if url == record.canonical_url:
                continue
            # Use the link's own line, rather than borrowing relevance from a
            # different paragraph elsewhere on the parent page.
            line = next((line for line in body.splitlines() if url in line), "")[:1000]
            score = sum(_matches(line.casefold(), term) for term in terms)
            if score and url not in candidates:
                candidates[url] = (score, {"url": url, "title": "Link from " + record.title[:200],
                    "snippet": "Navigation only, not factual evidence: " + line,
                    "discovery_date": None})
    return [row for _, row in sorted(candidates.values(), key=lambda item: -item[0])[:2]]
