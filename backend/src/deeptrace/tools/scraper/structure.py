"""Detect concrete code loss, rather than preferring a longer extraction."""

import re

from bs4 import BeautifulSoup


def missing_main_code(html: str, primary: str, fallback: str) -> bool:
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'nav', 'footer', 'header', 'form']):
        tag.decompose()
    root = soup.find('article') or soup.find('main')
    if root is None:
        return False

    def normalized(text):
        return re.sub(r'\s+', ' ', text).strip()

    primary_text, fallback_text = normalized(primary), normalized(fallback)
    for block in root.find_all('pre'):
        code = normalized(block.get_text('', strip=False))
        if len(code) >= 12 and code not in primary_text and code in fallback_text:
            return True
    return False
