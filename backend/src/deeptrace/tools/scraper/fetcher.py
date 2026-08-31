"""可靠网页抓取：HTTPX 提取失败时降级到 Playwright。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import httpx
import tiktoken
from trafilatura import extract

from deeptrace.models import RawDocument, ScraperUsed
from deeptrace.tools.scraper.urls import (
    normalize_url_before_fetch,
    resolve_document_identity,
    validate_public_url,
)


MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BENCHMARK_DNS_PROXY_NETWORK = ipaddress.ip_network("198.18.0.0/15")


@dataclass(frozen=True)
class ExtractionCandidate:
    """一次正文提取结果，来源字段用于准确记录 scraper_used。"""

    text: str
    title: str
    scraper_used: ScraperUsed
    source_url: str
    canonical_url: str | None = None


class WebFetchError(RuntimeError):
    """可安全回填到工具结果的结构化抓取错误。"""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {"code": self.code, "message": str(self), "details": self.details},
        }


def is_usable_text(
    text: str,
    count_tokens: Callable[[str], int],
    min_chars: int,
    min_tokens: int,
) -> bool:
    """正文必须同时通过字符数和 Token 数门槛。"""
    clean = text.strip()
    return len(clean) >= min_chars and count_tokens(clean) >= min_tokens


def is_allowed_dns_resolution(
    address_text: str, allow_benchmark_dns_proxy: bool
) -> bool:
    """判断域名解析地址是否可访问；基准网络只允许显式沙箱代理模式。"""
    address = ipaddress.ip_address(address_text)
    return address.is_global or (
        allow_benchmark_dns_proxy
        and address.version == 4
        and address in BENCHMARK_DNS_PROXY_NETWORK
    )


def select_best_extraction(
    candidates: list[ExtractionCandidate],
) -> ExtractionCandidate:
    """选最长正文；长度相同时保留更早的低成本路径。"""
    if not candidates:
        raise ValueError("至少需要一个正文候选")
    return max(candidates, key=lambda item: len(item.text.strip()))


class AsyncWebFetcher:
    """单次研究运行共享的异步抓取服务。"""

    def __init__(
        self,
        *,
        count_tokens: Callable[[str], int] | None = None,
        min_chars: int = 500,
        min_tokens: int = 200,
        max_page_chars: int = 20_000,
        http_timeout: float = 15.0,
        browser_timeout_ms: int = 15_000,
        max_redirects: int = 3,
        allow_benchmark_dns_proxy: bool = False,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        encoding = tiktoken.get_encoding("cl100k_base")
        self._count_tokens = count_tokens or (
            lambda text: len(encoding.encode(text, disallowed_special=()))
        )
        self._min_chars = min_chars
        self._min_tokens = min_tokens
        self._max_page_chars = max_page_chars
        self._http_timeout = http_timeout
        self._browser_timeout_ms = browser_timeout_ms
        self._max_redirects = max_redirects
        self._allow_benchmark_dns_proxy = allow_benchmark_dns_proxy
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(http_timeout),
            follow_redirects=False,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        )
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._browser_lock = asyncio.Lock()
        self._dns_cache: dict[str, bool] = {}

    async def fetch(self, url: str) -> RawDocument:
        """抓取公网 HTML 页面，正文质量不足时启动浏览器降级。"""
        try:
            normalized = normalize_url_before_fetch(url)
        except ValueError as exc:
            raise WebFetchError("unsafe_url", str(exc), url=url) from exc
        await self._ensure_public_url(normalized)

        candidates: list[ExtractionCandidate] = []
        http_error: WebFetchError | None = None
        try:
            html, final_url = await self._fetch_httpx(normalized)
            candidates.extend(self._extract_candidates(html, final_url, browser=False))
        except WebFetchError as exc:
            http_error = exc

        best = select_best_extraction(candidates) if candidates else None
        if best is None or not self._is_usable(best.text):
            try:
                html, final_url = await self._fetch_playwright(normalized)
                candidates.extend(
                    self._extract_candidates(html, final_url, browser=True)
                )
            except WebFetchError as browser_error:
                if best is None:
                    raise browser_error from http_error

        if not candidates:
            raise http_error or WebFetchError("empty_extraction", "未提取到正文")
        best = select_best_extraction(candidates)
        if not self._is_usable(best.text):
            raise WebFetchError(
                "insufficient_content",
                "正文未同时达到字符数和 Token 数门槛",
                chars=len(best.text.strip()),
                tokens=self._count_tokens(best.text.strip()),
            )

        full_content = best.text.strip()
        content_hash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
        final_url = normalize_url_before_fetch(best.source_url)
        canonical = self._safe_canonical_url(best.canonical_url, final_url)
        return RawDocument(
            doc_id=resolve_document_identity(final_url, canonical, content_hash),
            requested_url=normalized,
            final_url=final_url,
            canonical_url=canonical,
            title=best.title or final_url,
            content=full_content[: self._max_page_chars],
            content_hash=content_hash,
            fetched_at=datetime.now(timezone.utc),
            scraper_used=best.scraper_used,
            status="success",
        )

    async def _fetch_httpx(self, url: str) -> tuple[str, str]:
        current = url
        for redirect_count in range(self._max_redirects + 1):
            await self._ensure_public_url(current)
            try:
                async with self._http.stream(
                    "GET", current, timeout=self._http_timeout
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise WebFetchError(
                                "invalid_redirect", "重定向缺少 Location"
                            )
                        if redirect_count >= self._max_redirects:
                            raise WebFetchError(
                                "too_many_redirects", "重定向次数超过限制"
                            )
                        current = normalize_url_before_fetch(
                            urljoin(str(response.url), location)
                        )
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" not in content_type:
                        raise WebFetchError(
                            "unsupported_content_type",
                            "只支持 text/html 页面",
                            content_type=content_type,
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise WebFetchError(
                                "response_too_large",
                                "响应大小超过限制",
                                max_bytes=MAX_RESPONSE_BYTES,
                            )
                    return body.decode(
                        response.encoding or "utf-8", errors="replace"
                    ), str(response.url)
            except WebFetchError:
                raise
            except httpx.HTTPError as exc:
                raise WebFetchError(
                    "http_failed", f"HTTP 请求失败：{type(exc).__name__}"
                ) from exc
        raise WebFetchError("too_many_redirects", "重定向次数超过限制")

    async def _fetch_playwright(self, url: str) -> tuple[str, str]:
        await self._ensure_browser()
        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            user_agent=DEFAULT_USER_AGENT,
        )
        page = await context.new_page()

        async def guard_request(route: Any, request: Any) -> None:
            if request.resource_type in {"image", "media", "font"}:
                await route.abort()
                return
            if request.url.startswith(("http://", "https://")):
                try:
                    await self._ensure_public_url(request.url)
                except WebFetchError:
                    await route.abort()
                    return
            await route.continue_()

        await page.route("**/*", guard_request)
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self._browser_timeout_ms,
            )
            await self._ensure_public_url(page.url)
            html = await page.content()
            if len(html.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise WebFetchError(
                    "response_too_large", "浏览器渲染后的页面超过大小限制"
                )
            return html, page.url
        except WebFetchError:
            raise
        except Exception as exc:
            raise WebFetchError(
                "browser_failed", f"浏览器抓取失败：{type(exc).__name__}"
            ) from exc
        finally:
            await context.close()

    async def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        async with self._browser_lock:
            if self._browser is not None:
                return
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
            except Exception as exc:
                if self._playwright is not None:
                    await self._playwright.stop()
                    self._playwright = None
                raise WebFetchError(
                    "browser_unavailable",
                    "Chromium 不可用，请运行：uv run playwright install chromium",
                ) from exc

    async def _ensure_public_url(self, url: str) -> None:
        allowed, reason = validate_public_url(url)
        if not allowed:
            raise WebFetchError("unsafe_url", reason, url=url)
        hostname = (urlsplit(url).hostname or "").lower()
        if hostname in self._dns_cache:
            if not self._dns_cache[hostname]:
                raise WebFetchError("unsafe_url", "域名解析到非公网地址", url=url)
            return
        try:
            records = await asyncio.to_thread(
                socket.getaddrinfo, hostname, None, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise WebFetchError("dns_failed", "域名解析失败", url=url) from exc
        is_public = bool(records) and all(
            is_allowed_dns_resolution(
                record[4][0], self._allow_benchmark_dns_proxy
            )
            for record in records
        )
        self._dns_cache[hostname] = is_public
        if not is_public:
            raise WebFetchError("unsafe_url", "域名解析到非公网地址", url=url)

    def _extract_candidates(
        self, html: str, source_url: str, *, browser: bool
    ) -> list[ExtractionCandidate]:
        title, canonical = self._metadata(html)
        trafilatura_text = extract(
            html,
            url=source_url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        trafilatura_used = (
            ScraperUsed.PLAYWRIGHT_TRAFILATURA
            if browser
            else ScraperUsed.HTTPX_TRAFILATURA
        )
        bs4_used = ScraperUsed.PLAYWRIGHT_BS4 if browser else ScraperUsed.HTTPX_BS4
        return [
            ExtractionCandidate(
                text=(trafilatura_text or "").strip(),
                title=title,
                scraper_used=trafilatura_used,
                source_url=source_url,
                canonical_url=canonical,
            ),
            ExtractionCandidate(
                text=self._extract_bs4(html),
                title=title,
                scraper_used=bs4_used,
                source_url=source_url,
                canonical_url=canonical,
            ),
        ]

    @staticmethod
    def _metadata(html: str) -> tuple[str, str | None]:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        canonical_tag = soup.find(
            "link", rel=lambda value: value and "canonical" in value
        )
        canonical = canonical_tag.get("href") if canonical_tag else None
        return title, str(canonical).strip() if canonical else None

    @staticmethod
    def _extract_bs4(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(
            ["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]
        ):
            tag.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        return "\n".join(
            line
            for line in (part.strip() for part in root.get_text("\n").splitlines())
            if line
        )

    @staticmethod
    def _safe_canonical_url(
        canonical_url: str | None, final_url: str
    ) -> str | None:
        if not canonical_url:
            return None
        try:
            canonical = normalize_url_before_fetch(urljoin(final_url, canonical_url))
        except ValueError:
            return None
        allowed, _ = validate_public_url(canonical)
        if not allowed:
            return None
        final_host = (urlsplit(final_url).hostname or "").lower()
        canonical_host = (urlsplit(canonical).hostname or "").lower()

        def desktop_host(host: str) -> str:
            for prefix in ("m.", "mobile."):
                if host.startswith(prefix):
                    return host[len(prefix) :]
            return host

        if desktop_host(final_host) != desktop_host(canonical_host):
            return None
        return canonical

    def _is_usable(self, text: str) -> bool:
        return is_usable_text(
            text, self._count_tokens, self._min_chars, self._min_tokens
        )

    async def aclose(self) -> None:
        """关闭浏览器及由本服务创建的 HTTP 客户端。"""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        if self._owns_http:
            await self._http.aclose()
