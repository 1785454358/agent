"""Canonical tool error taxonomy shared by the domain and the tool gateway."""

from __future__ import annotations

from deeptrace.domain.execution import ErrorCategory


_CATEGORY_BY_CODE: dict[str, ErrorCategory] = {
    # Transient infrastructure failures: retried once inside the gateway.
    "provider_timeout": ErrorCategory.TRANSIENT,
    "http_failed": ErrorCategory.TRANSIENT,
    "dns_failed": ErrorCategory.TRANSIENT,
    # Semantic failures the model can react to by changing its next action.
    "unsafe_url": ErrorCategory.AGENT_RECOVERABLE,
    "empty_extraction": ErrorCategory.AGENT_RECOVERABLE,
    "empty_page": ErrorCategory.AGENT_RECOVERABLE,
    "insufficient_content": ErrorCategory.AGENT_RECOVERABLE,
    "unsupported_content_type": ErrorCategory.AGENT_RECOVERABLE,
    "no_search_results": ErrorCategory.AGENT_RECOVERABLE,
    "search_failed": ErrorCategory.AGENT_RECOVERABLE,
    "too_many_redirects": ErrorCategory.AGENT_RECOVERABLE,
    "invalid_redirect": ErrorCategory.AGENT_RECOVERABLE,
    "response_too_large": ErrorCategory.AGENT_RECOVERABLE,
    "malformed_search_preview": ErrorCategory.AGENT_RECOVERABLE,
    "search_skipped": ErrorCategory.AGENT_RECOVERABLE,
    "browser_failed": ErrorCategory.AGENT_RECOVERABLE,
    # Validation failures: fixable by correcting arguments, never retried as-is.
    "invalid_arguments": ErrorCategory.VALIDATION,
    "invalid_query": ErrorCategory.VALIDATION,
    "memory_disabled": ErrorCategory.VALIDATION,
    # Policy failures: never retried.
    "tool_not_registered": ErrorCategory.POLICY,
    "tool_not_allowed": ErrorCategory.POLICY,
    "url_not_authorized": ErrorCategory.POLICY,
    "unsafe_arguments": ErrorCategory.POLICY,
    "budget_exhausted": ErrorCategory.POLICY,
    # Fatal failures: recorded, never retried, may terminate the branch.
    "tool_internal_error": ErrorCategory.FATAL,
    "provider_error": ErrorCategory.FATAL,
    "missing_evidence": ErrorCategory.FATAL,
    "unexpected_evidence": ErrorCategory.FATAL,
    "invalid_adapter_result": ErrorCategory.FATAL,
    "shared_execution_failed": ErrorCategory.FATAL,
    "execution_abandoned": ErrorCategory.FATAL,
    "browser_unavailable": ErrorCategory.FATAL,
}

_MESSAGE_BY_CODE: dict[str, str] = {
    "provider_timeout": "工具调用超时，系统已重试；如仍失败可稍后重试。",
    "http_failed": "网络请求失败，系统已重试；如仍失败可更换来源。",
    "dns_failed": "域名解析失败，可更换来源或稍后重试。",
    "unsafe_url": "该 URL 不安全或不是公网地址，请改用其他来源。",
    "empty_extraction": "页面未提取到正文，请更换来源。",
    "empty_page": "页面内容为空，请更换来源。",
    "insufficient_content": "页面正文过少，请更换来源。",
    "unsupported_content_type": "仅支持 HTML 页面，请更换来源。",
    "no_search_results": "没有搜索到结果，请改用更具体或同义的查询。",
    "search_failed": "搜索服务返回失败，请调整查询或稍后重试。",
    "too_many_redirects": "重定向次数过多，请更换来源。",
    "invalid_redirect": "重定向缺少目标地址，请更换来源。",
    "response_too_large": "页面体积超过限制，请更换来源。",
    "malformed_search_preview": "搜索结果格式异常，请调整查询后重试。",
    "search_skipped": "本次搜索被跳过，请重新发起查询。",
    "browser_failed": "该页面无法用浏览器抓取，请更换来源。",
    "browser_unavailable": "抓取浏览器不可用，请检查服务配置（playwright install chromium）。",
    "invalid_arguments": "参数不合法，请修正参数后重试。",
    "invalid_query": "查询词不合法，请改写查询后重试。",
    "memory_disabled": "记忆检索当前不可用，请改用其他信息源。",
    "tool_not_registered": "该工具不可用，请改用其他工具。",
    "tool_not_allowed": "当前角色不允许调用该工具。",
    "url_not_authorized": "该 URL 未获授权抓取，请先通过搜索获得该来源。",
    "unsafe_arguments": "参数未通过安全检查，请修正后重试。",
    "budget_exhausted": "工具预算已耗尽，请基于现有资料收尾。",
    "tool_internal_error": "工具内部错误，已记录，请勿重复调用同一请求。",
}


def classify_error_code(code: str) -> ErrorCategory:
    """Map a tool error code to its category, defaulting to fatal."""
    return _CATEGORY_BY_CODE.get(code, ErrorCategory.FATAL)


def is_retryable(category: ErrorCategory) -> bool:
    """Only transient infrastructure failures are retried inside the gateway."""
    return category is ErrorCategory.TRANSIENT


def error_message_for(code: str) -> str:
    """Model-facing, sanitized remediation hint for an error code."""
    return _MESSAGE_BY_CODE.get(code, f"工具调用失败（{code}）。")
