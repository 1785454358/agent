from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit, urlunsplit

from deeptrace.domain import ResearchMode, ResponseMode, ToolName
from deeptrace.tools.contracts import ToolCapability, ToolSpec
from deeptrace.tools.registry import ToolRegistry
from deeptrace.tools.scraper.urls import normalize_url_before_fetch, validate_public_url


MAX_CALLER_ID_LENGTH = 128
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_NON_PUBLIC_SUFFIXES = (".internal", ".lan", ".local", ".localhost", ".home")


class CallerRole(StrEnum):
    WORKFLOW_GRAPH = "workflow_graph"
    PLAN_EXECUTE_EXECUTOR = "plan_execute_executor"
    MULTI_AGENT_RESEARCHER = "multi_agent_researcher"
    MULTI_AGENT_SUPERVISOR = "multi_agent_supervisor"
    RESPONSE_GRAPH = "response_graph"
    MEMORY_CONSOLIDATION = "memory_consolidation"


_ROLE_MODES: dict[CallerRole, ResearchMode] = {
    CallerRole.WORKFLOW_GRAPH: ResearchMode.WORKFLOW,
    CallerRole.PLAN_EXECUTE_EXECUTOR: ResearchMode.PLAN_EXECUTE,
    CallerRole.MULTI_AGENT_RESEARCHER: ResearchMode.MULTI_AGENT,
    CallerRole.MULTI_AGENT_SUPERVISOR: ResearchMode.MULTI_AGENT,
}


@dataclass(frozen=True)
class ToolCaller:
    caller_id: str
    role: CallerRole
    mode: ResearchMode | None = None
    response_mode: ResponseMode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.caller_id, str) or not self.caller_id.strip():
            raise ValueError("caller_id must be a non-empty string")
        if len(self.caller_id) > MAX_CALLER_ID_LENGTH:
            raise ValueError(f"caller_id exceeds {MAX_CALLER_ID_LENGTH} characters")
        if not isinstance(self.role, CallerRole):
            raise TypeError("role must be a CallerRole")
        if self.mode is not None and not isinstance(self.mode, ResearchMode):
            raise TypeError("mode must be a ResearchMode")
        if self.response_mode is not None and not isinstance(
            self.response_mode, ResponseMode
        ):
            raise TypeError("response_mode must be a ResponseMode")

        required_mode = _ROLE_MODES.get(self.role)
        if required_mode is not None and self.mode is not required_mode:
            raise ValueError(f"{self.role.value} requires mode {required_mode.value}")
        if self.role is CallerRole.RESPONSE_GRAPH:
            if self.mode is None:
                raise ValueError("response_graph requires a research mode")
            if self.response_mode is None:
                raise ValueError("response_graph requires a response_mode")
        elif self.response_mode is not None:
            raise ValueError(f"{self.role.value} cannot set response_mode")
        if self.role is CallerRole.MEMORY_CONSOLIDATION and self.mode is not None:
            raise ValueError("memory_consolidation cannot set a research mode")


class ToolAllowlistPolicy(Protocol):
    def resolve(
        self,
        registry: ToolRegistry,
        caller: ToolCaller,
        tool: ToolName,
    ) -> ToolSpec: ...


_ALLOWED_CAPABILITIES: dict[CallerRole, frozenset[ToolCapability]] = {
    CallerRole.WORKFLOW_GRAPH: frozenset(
        {
            ToolCapability.WEB_SEARCH,
            ToolCapability.PAGE_FETCH,
            ToolCapability.MEMORY_READ,
        }
    ),
    CallerRole.PLAN_EXECUTE_EXECUTOR: frozenset(
        {
            ToolCapability.WEB_SEARCH,
            ToolCapability.PAGE_FETCH,
            ToolCapability.MEMORY_READ,
        }
    ),
    CallerRole.MULTI_AGENT_RESEARCHER: frozenset(
        {
            ToolCapability.WEB_SEARCH,
            ToolCapability.PAGE_FETCH,
            ToolCapability.MEMORY_READ,
        }
    ),
    CallerRole.MULTI_AGENT_SUPERVISOR: frozenset(),
    CallerRole.RESPONSE_GRAPH: frozenset({ToolCapability.EVIDENCE_READ}),
    CallerRole.MEMORY_CONSOLIDATION: frozenset(
        {ToolCapability.MEMORY_READ, ToolCapability.MEMORY_WRITE}
    ),
}


class StaticToolAllowlist:
    def resolve(
        self,
        registry: ToolRegistry,
        caller: ToolCaller,
        tool: ToolName,
    ) -> ToolSpec:
        if not isinstance(caller, ToolCaller):
            raise TypeError("caller must be a ToolCaller")
        spec = registry.resolve(tool)
        if spec.capability not in _ALLOWED_CAPABILITIES[caller.role]:
            raise PermissionError(
                f"caller is not allowed to use capability: {spec.capability.value}"
            )
        return spec


class UrlAuthorizationSource(StrEnum):
    SEARCH_RESULT = "search_result"
    MEMORY_RESULT = "memory_result"
    DIRECT_USER_INPUT = "direct_user_input"
    AGENT_DISCOVERED = "agent_discovered"


@dataclass(frozen=True)
class UrlAuthorization:
    source: UrlAuthorizationSource
    urls: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.source, UrlAuthorizationSource):
            raise TypeError("source must be a UrlAuthorizationSource")
        if not isinstance(self.urls, frozenset) or not self.urls:
            raise ValueError("urls must be a non-empty frozenset")
        if any(not isinstance(url, str) or not url.strip() for url in self.urls):
            raise ValueError("authorized URLs must be non-empty strings")


class UrlSecurityPolicy(Protocol):
    def validate(
        self,
        tool: ToolName,
        arguments: Mapping[str, Any],
        authorization: UrlAuthorization | None,
    ) -> dict[str, Any]: ...


class DeterministicUrlSecurityPolicy:
    def validate(
        self,
        tool: ToolName,
        arguments: Mapping[str, Any],
        authorization: UrlAuthorization | None,
    ) -> dict[str, Any]:
        if not isinstance(tool, ToolName):
            raise TypeError("tool must be a ToolName")
        copied = dict(arguments)
        if tool is not ToolName.FETCH_PAGE:
            return copied

        raw_url = copied.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ValueError("fetch URL must be a non-empty string")
        normalized = self._normalize_public_url(raw_url)
        if authorization is None:
            raise PermissionError("fetch URL is not authorized")
        if not isinstance(authorization, UrlAuthorization):
            raise TypeError("authorization must be a UrlAuthorization")
        approved = {
            self._normalize_public_url(candidate) for candidate in authorization.urls
        }
        if normalized not in approved:
            raise PermissionError("fetch URL is not authorized")
        copied["url"] = normalized
        return copied

    @staticmethod
    def _normalize_public_url(url: str) -> str:
        try:
            parsed = urlsplit(url.strip())
            port = parsed.port
        except ValueError as exc:
            raise ValueError("fetch URL is invalid") from exc
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError("fetch URL uses an unsupported scheme")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("fetch URL cannot contain credentials")

        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname or any(ord(character) > 127 for character in hostname):
            raise ValueError("fetch URL has an invalid host")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            if all(character.isdigit() or character == "." for character in hostname):
                raise ValueError("fetch URL host is not public")
            if "." not in hostname or hostname.endswith(_NON_PUBLIC_SUFFIXES):
                raise ValueError("fetch URL host is not public")
            if any(not _DOMAIN_LABEL.fullmatch(label) for label in hostname.split(".")):
                raise ValueError("fetch URL has an invalid host")
        else:
            if not address.is_global:
                raise ValueError("fetch URL host is not public")

        host = f"[{hostname}]" if ":" in hostname else hostname
        if port is not None:
            host = f"{host}:{port}"
        without_credentials = urlunsplit(
            (parsed.scheme.lower(), host, parsed.path, parsed.query, parsed.fragment)
        )
        safe, _reason = validate_public_url(without_credentials)
        if not safe:
            raise ValueError("fetch URL host is not public")
        return normalize_url_before_fetch(without_credentials)
