"""Preserve observed alternate formats without inventing or widening URLs."""

import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from deeptrace.tools.scraper.urls import normalize_url_before_fetch, validate_public_url

FORMATS_LABEL = "Observed document formats (navigation only):"


def document_format_links(html, source_url):
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("main") or soup.find("article") or soup.body or soup
    result = []
    for anchor in root.find_all("a", href=True):
        if anchor.find_parent(["nav", "footer", "header", "aside"]):
            continue
        label = anchor.get_text(" ", strip=True)
        if not re.fullmatch(r"(?:HTML|TXT|plain text|full text|HTML full text|TXT full text)", label, re.I):
            continue
        raw = urljoin(source_url, str(anchor["href"]))
        if not validate_public_url(raw)[0] or urlsplit(raw).hostname != urlsplit(source_url).hostname:
            continue
        url = normalize_url_before_fetch(raw)
        if url != normalize_url_before_fetch(source_url) and url not in result:
            result.append(url)
        if len(result) >= 6:
            break
    return result
