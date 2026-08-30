"""网页抓取前的 URL 规范化与抓取后的文档身份计算。"""

from __future__ import annotations

import hashlib
import ipaddress
import posixpath
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


_TRACKING_PARAMS = {"gclid", "fbclid"}


def normalize_url_before_fetch(url: str) -> str:
    """执行保守规范化，不提前合并协议或移动端域名。"""
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL 无法解析") from exc
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not scheme or not hostname:
        raise ValueError("URL 必须包含协议和主机名")

    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = posixpath.normpath(parsed.path or "/")
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/":
        path = path.rstrip("/")
    path = quote(path, safe="/:@!$&'()*+,;=~-._%")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in _TRACKING_PARAMS
    ]
    return urlunsplit(
        (scheme, host, path, urlencode(sorted(query_items), doseq=True), "")
    )


def validate_public_url(url: str) -> tuple[bool, str]:
    """拒绝明显不安全的协议、凭据、本地域名和非公网 IP。"""
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        return False, "URL 无法解析"
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "只允许 http 和 https 协议"
    if parsed.username is not None or parsed.password is not None:
        return False, "URL 不允许包含用户凭据"
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
        return False, "不允许访问本地主机"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True, ""
    return (True, "") if address.is_global else (False, "不允许访问非公网 IP")


def resolve_document_identity(
    final_url: str, canonical_url: str | None, content_hash: str
) -> str:
    """优先按正文哈希识别同页；无正文时再使用 canonical/final URL。"""
    if content_hash:
        payload = f"content:{content_hash}"
    else:
        payload = f"url:{normalize_url_before_fetch(canonical_url or final_url)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
