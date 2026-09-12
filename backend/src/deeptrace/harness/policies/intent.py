"""Deterministic intent and context-window policies for the runtime graph."""

from __future__ import annotations

import re

from deeptrace.domain import ConversationIntent, ResponseMode
from deeptrace.responses.citations import select_response_mode


_MEMORY_PATTERNS = (
    re.compile(r"记住"),
    re.compile(r"记住我"),
    re.compile(r"以后(都|要|请)?(用|按)"),
    re.compile(r"我的偏好"),
)
_SWITCH_PATTERNS = (
    re.compile(r"切换(到|为|成).{0,8}(模式|workflow|plan_execute|multi_agent)", re.IGNORECASE),
    re.compile(r"(用|改用|换成).{0,8}plan.?execute", re.IGNORECASE),
    re.compile(r"(用|改用|换成)多智能体"),
)
_INCREMENTAL_PATTERNS = (
    re.compile(r"再查"),
    re.compile(r"补充(一下|些)"),
    re.compile(r"更新一下"),
    re.compile(r"最新(的|进展|消息)"),
    re.compile(r"继续(搜索|研究|查)"),
)
_FOLLOW_UP_PATTERNS = (
    re.compile(r"总结一下"),
    re.compile(r"继续(解释|说|聊)"),
    re.compile(r"为什么"),
    re.compile(r"上面(提到|说|的)"),
    re.compile(r"刚才(提到|说|的)"),
    re.compile(r"展开(讲|说)"),
    re.compile(r"什么意思"),
)


def classify_intent(user_input: str, *, prior_evidence: bool) -> ConversationIntent:
    """Boundary policy: explicit intents first, then follow-up vs research."""
    text = (user_input or "").strip().lower()
    if not text:
        return ConversationIntent.CONVERSATION

    if any(pattern.search(text) for pattern in _MEMORY_PATTERNS):
        return ConversationIntent.MEMORY_UPDATE
    if any(pattern.search(text) for pattern in _SWITCH_PATTERNS):
        return ConversationIntent.SWITCH_MODE
    if any(pattern.search(text) for pattern in _INCREMENTAL_PATTERNS):
        if prior_evidence:
            return ConversationIntent.INCREMENTAL_RESEARCH
        return ConversationIntent.RESEARCH
    if any(pattern.search(text) for pattern in _FOLLOW_UP_PATTERNS):
        if prior_evidence:
            return ConversationIntent.CONVERSATION
        return ConversationIntent.RESEARCH

    output_mode = select_response_mode(text)
    if output_mode is ResponseMode.REPORT:
        if prior_evidence:
            return ConversationIntent.REPORT_REQUEST
        return ConversationIntent.RESEARCH
    return ConversationIntent.RESEARCH


def response_mode_for_intent(
    intent: ConversationIntent, user_input: str
) -> ResponseMode:
    """Direct-response turns keep their explicit output form; research turns decide later."""
    if intent is ConversationIntent.REPORT_REQUEST:
        return select_response_mode(user_input)
    if intent is ConversationIntent.CONVERSATION:
        return select_response_mode(user_input)
    return ResponseMode.ANSWER
