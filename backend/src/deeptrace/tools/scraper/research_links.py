"""Preserve explicit scholarly anchors; never invent a publication URL."""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from deeptrace.tools.scraper.urls import normalize_url_before_fetch, validate_public_url

RESEARCH_LINKS_LABEL = "Original research links (HTML anchors):"


def is_paper_link(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower()
    return (
        host in {"doi.org", "dx.doi.org"} and parsed.path.startswith("/10.")
    ) or (host == "arxiv.org" and parsed.path.startswith(("/abs/", "/html/", "/pdf/"))) or (
        bool(host) and parsed.path.lower().endswith(".pdf")
    )


def arxiv_identity(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    if parsed.hostname != "arxiv.org":
        return None
    match = re.fullmatch(r"/(?:abs|html|pdf)/(\d{4}\.\d{4,5}|[a-z.-]+/\d{7})(v\d+)?(?:\.pdf)?", parsed.path)
    return (match[1], match[2] or "") if match else None


def acquisition_links(source_url: str, body: str) -> list[str]:
    """Distinguish a paper's identity from its abstract/full-text representation."""
    links = primary_links_in_body(body)
    source = arxiv_identity(source_url)
    if source is not None:
        if not urlsplit(source_url).path.startswith("/abs/"):
            return []  # Do not follow citations from a full paper.
        links = [url for url in links
                 if (identity := arxiv_identity(url)) is not None
                 and identity[0] == source[0] and (not source[1] or identity[1] == source[1])
                 and urlsplit(url).path.startswith(("/html/", "/pdf/"))]
    elif is_paper_link(source_url):
        links = [url for url in links if urlsplit(url).path.lower().endswith(".pdf")]
    return sorted(links, key=lambda url: (not urlsplit(url).path.startswith("/html/"),
                                         not urlsplit(url).path.lower().endswith(".pdf")))


def original_research_links(html: str, source_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("main") or soup.find("article") or soup.body or soup
    links = []
    for anchor in container.find_all("a", href=True):
        if anchor.find_parent(["nav", "footer", "header", "aside"]):
            continue
        parents = list(anchor.parents)
        if any(
            re.search(r"references|bibliography", str(p.get("id", "")) + " " + " ".join(p.get("class", [])), re.IGNORECASE)
            for p in parents if getattr(p, "attrs", None)
        ):
            continue
        preceding = anchor.find_previous(["h2", "h3", "h4"])
        if preceding and re.fullmatch(r"references|bibliography", preceding.get_text(strip=True), re.IGNORECASE):
            continue
        try:
            raw = urljoin(source_url, str(anchor["href"]))
            if not validate_public_url(raw)[0]:
                continue
            url = normalize_url_before_fetch(raw)
        except (ValueError, TypeError):
            continue
        if url != source_url and is_paper_link(url) and url not in links:
            links.append(url)
        if len(links) == 6:
            break
    return links


def primary_links_in_body(body: str) -> list[str]:
    if RESEARCH_LINKS_LABEL not in body:
        return []
    section = body.rsplit(RESEARCH_LINKS_LABEL, 1)[1]
    return [line.strip() for line in section.splitlines()[:7] if is_paper_link(line.strip())]
