from __future__ import annotations

import socket
from typing import ClassVar

import pytest
from pydantic import BaseModel, Field, model_validator

from deeptrace.domain import ResearchProfile, ResponseProfile, ToolName
from deeptrace.tools.contracts import CachePolicy, ToolCapability, ToolSpec
from deeptrace.tools.policy import (
    CallerRole,
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
    ToolCaller,
    UrlAuthorization,
    UrlAuthorizationSource,
)
from deeptrace.tools.registry import ToolRegistry


class TrapArguments(BaseModel):
    validations: ClassVar[int] = 0
    value: str = Field(min_length=1)

    @model_validator(mode="after")
    def count_validation(self) -> "TrapArguments":
        type(self).validations += 1
        return self


async def _handler(arguments: BaseModel) -> dict[str, str]:
    raise AssertionError(f"handler must not run during access checks: {arguments}")


def _spec(name: ToolName, capability: ToolCapability) -> ToolSpec:
    return ToolSpec(
        name=name,
        argument_model=TrapArguments,
        handler=_handler,
        capability=capability,
        cache_policy=CachePolicy.SUCCESS,
        timeout_seconds=5.0,
        preview_limit=200,
        stores_evidence=True,
    )


def _caller(
    role: CallerRole,
    profile: ResearchProfile | None = None,
    response_profile: ResponseProfile | None = None,
) -> ToolCaller:
    return ToolCaller(
        caller_id=f"caller-{role.value}",
        role=role,
        profile=profile,
        response_profile=response_profile,
    )


@pytest.fixture(autouse=True)
def _reset_validation_counter() -> None:
    TrapArguments.validations = 0


@pytest.fixture
def registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_spec(ToolName.SEARCH_WEB, ToolCapability.WEB_SEARCH))
    registry.register(_spec(ToolName.FETCH_PAGE, ToolCapability.PAGE_FETCH))
    registry.register(_spec(ToolName.SEARCH_MEMORY, ToolCapability.MEMORY_READ))
    return registry


@pytest.mark.parametrize(
    ("caller", "tool"),
    [
        (_caller(CallerRole.WORKFLOW_GRAPH, ResearchProfile.WORKFLOW), ToolName.SEARCH_WEB),
        (_caller(CallerRole.WORKFLOW_GRAPH, ResearchProfile.WORKFLOW), ToolName.FETCH_PAGE),
        (_caller(CallerRole.PLAN_EXECUTE_EXECUTOR, ResearchProfile.PLAN_EXECUTE), ToolName.SEARCH_MEMORY),
        (_caller(CallerRole.MULTI_AGENT_RESEARCHER, ResearchProfile.MULTI_AGENT), ToolName.SEARCH_WEB),
    ],
)
def test_allowlist_resolves_research_tools_for_authorized_callers(
    registry: ToolRegistry, caller: ToolCaller, tool: ToolName
) -> None:
    policy = StaticToolAllowlist()

    assert policy.resolve(registry, caller, tool).name is tool


@pytest.mark.parametrize(
    "caller",
    [
        _caller(CallerRole.MULTI_AGENT_SUPERVISOR, ResearchProfile.MULTI_AGENT),
        _caller(
            CallerRole.RESPONSE_GRAPH,
            ResearchProfile.WORKFLOW,
            ResponseProfile.ANSWER,
        ),
    ],
)
def test_disallowed_callers_fail_before_argument_validation(
    registry: ToolRegistry, caller: ToolCaller
) -> None:
    policy = StaticToolAllowlist()

    with pytest.raises(PermissionError, match="caller is not allowed"):
        policy.resolve(registry, caller, ToolName.SEARCH_WEB)

    assert TrapArguments.validations == 0


def test_unknown_tool_fails_before_argument_validation(registry: ToolRegistry) -> None:
    policy = StaticToolAllowlist()
    caller = _caller(CallerRole.WORKFLOW_GRAPH, ResearchProfile.WORKFLOW)

    with pytest.raises(KeyError, match="tool is not registered"):
        policy.resolve(ToolRegistry(), caller, ToolName.SEARCH_MEMORY)

    assert TrapArguments.validations == 0


@pytest.mark.parametrize(
    ("role", "profile", "response_profile", "message"),
    [
        ("workflow_graph", ResearchProfile.WORKFLOW, None, "role must be a CallerRole"),
        (CallerRole.WORKFLOW_GRAPH, "workflow", None, "profile must be a ResearchProfile"),
        (CallerRole.WORKFLOW_GRAPH, ResearchProfile.PLAN_EXECUTE, None, "requires profile workflow"),
        (CallerRole.RESPONSE_GRAPH, ResearchProfile.WORKFLOW, None, "requires a response_profile"),
        (CallerRole.MULTI_AGENT_SUPERVISOR, ResearchProfile.MULTI_AGENT, ResponseProfile.ANSWER, "cannot set response_profile"),
    ],
)
def test_caller_identity_rejects_inconsistent_or_raw_enums(
    role: object,
    profile: object,
    response_profile: object,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        ToolCaller(
            caller_id="caller-1",
            role=role,  # type: ignore[arg-type]
            profile=profile,  # type: ignore[arg-type]
            response_profile=response_profile,  # type: ignore[arg-type]
        )


def _authorization(url: str) -> UrlAuthorization:
    return UrlAuthorization(
        source=UrlAuthorizationSource.SEARCH_RESULT,
        urls=frozenset({url}),
    )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "http://user:secret@example.com/page",
        "http://127.0.0.1/admin",
        "http://127.1/admin",
        "http://2130706433/admin",
        "http://[::1]/admin",
        "http://10.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://service.local/admin",
        "http://intranet/admin",
    ],
)
def test_url_policy_rejects_unsafe_fetch_targets(url: str) -> None:
    policy = DeterministicUrlSecurityPolicy()

    with pytest.raises(ValueError, match="fetch URL"):
        policy.validate(ToolName.FETCH_PAGE, {"url": url}, _authorization(url))


def test_url_policy_requires_trusted_provenance_and_exact_normalized_match() -> None:
    policy = DeterministicUrlSecurityPolicy()
    authorization = _authorization("https://example.com/news?a=1&b=2")

    with pytest.raises(PermissionError, match="not authorized"):
        policy.validate(
            ToolName.FETCH_PAGE,
            {"url": "https://example.com/other"},
            authorization,
        )

    assert policy.validate(
        ToolName.FETCH_PAGE,
        {"url": "HTTPS://Example.COM/news/?b=2&utm_source=x&a=1#top"},
        authorization,
    ) == {"url": "https://example.com/news?a=1&b=2"}


@pytest.mark.parametrize(
    "source",
    [
        UrlAuthorizationSource.SEARCH_RESULT,
        UrlAuthorizationSource.MEMORY_RESULT,
        UrlAuthorizationSource.DIRECT_USER_INPUT,
    ],
)
def test_url_policy_accepts_each_trusted_source_without_dns(
    monkeypatch: pytest.MonkeyPatch,
    source: UrlAuthorizationSource,
) -> None:
    def fail_dns(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"DNS must not be called: {args}, {kwargs}")

    monkeypatch.setattr(socket, "getaddrinfo", fail_dns)
    policy = DeterministicUrlSecurityPolicy()
    authorization = UrlAuthorization(
        source=source,
        urls=frozenset({"https://example.com/article"}),
    )

    assert policy.validate(
        ToolName.FETCH_PAGE,
        {"url": "https://example.com/article"},
        authorization,
    )["url"] == "https://example.com/article"


def test_url_policy_leaves_non_fetch_arguments_unchanged() -> None:
    policy = DeterministicUrlSecurityPolicy()
    arguments = {"query": "langgraph harness"}

    assert policy.validate(ToolName.SEARCH_WEB, arguments, None) == arguments


def test_url_authorization_rejects_raw_source_enum() -> None:
    with pytest.raises(TypeError, match="source must be a UrlAuthorizationSource"):
        UrlAuthorization(
            source="search_result",  # type: ignore[arg-type]
            urls=frozenset({"https://example.com/article"}),
        )
