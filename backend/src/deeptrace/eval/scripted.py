"""A deterministic model gateway so Tier 1 runs with zero external calls.

It plays every role the strategies ask for: it plans, searches, fetches, updates
todos and answers. The behaviour is intentionally simple and stable so that
Tier 1 measures the pipeline and the corpus, not model quality. Real-model
quality is a Tier 2 (``real``) concern.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage

from deeptrace.domain import ToolName
from deeptrace.harness.agent_tools import WRITE_TODOS_TOOL

_TASK_RE = re.compile(r"原始任务：\n(.*?)\n当前约束：", re.DOTALL)


def _tool_payload(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _validate_envelope(messages: list[Any]) -> None:
    has_system = any(
        getattr(message, "type", None) == "system"
        and str(getattr(message, "content", "")).strip()
        for message in messages
    )
    joined = "\n".join(str(getattr(message, "content", "")) for message in messages)
    if not has_system or "原始任务：" not in joined or "当前约束：" not in joined:
        raise ValueError("model_context_invariant violated in eval model gateway")


def _question(messages: list[Any]) -> str:
    joined = "\n".join(str(getattr(message, "content", "")) for message in messages)
    match = _TASK_RE.search(joined)
    return match.group(1).strip() if match else joined.strip()


class ScriptedResearchModel:
    """Implements the ``ModelGateway`` protocol deterministically."""

    def __init__(self, *, max_fetches: int = 2) -> None:
        if max_fetches < 1:
            raise ValueError("max_fetches must be positive")
        self._max_fetches = max_fetches
        self._call_seq = 0
        self.roles: list[str] = []

    async def invoke(self, *, role: str, messages: list[Any], tools=None) -> Any:
        _validate_envelope(messages)
        self.roles.append(role)
        if role == "researcher":
            return self._researcher(messages)
        payload = self._strategy_payload(role, messages)
        return json.dumps(payload, ensure_ascii=False)

    # -- role handlers ---------------------------------------------------

    def _strategy_payload(self, role: str, messages: list[Any]) -> dict[str, Any]:
        question = _question(messages)
        if role in {"planner", "supervisor"}:
            key = "assignments" if role == "supervisor" else "queries"
            return {
                key: [question],
                "query_targets": {question: ["r1"]},
                "requirements": [
                    {"id": "r1", "description": "完整回答原始问题及全部用户约束"}
                ],
            }
        if role in {"replanner", "follow_up"}:
            key = "assignments" if role == "follow_up" else "queries"
            return {key: []}
        if role == "summarizer":
            return {
                "topic": question[:200],
                "user_constraints": [],
                "established_facts": [],
                "referenced_entities": {},
                "unresolved_questions": [],
                "previous_conclusions": [],
            }
        if role == "responder":
            return {"content": "根据已收集的资料，可以给出结论 [1]。"}
        if role == "evaluator":
            return self._evaluation(messages)
        raise ValueError(f"unexpected eval model role: {role}")

    @staticmethod
    def _evaluation(messages: list[Any]) -> dict[str, Any]:
        joined = "\n".join(str(getattr(message, "content", "")) for message in messages)
        view = json.JSONDecoder().raw_decode(
            joined.rsplit("\nEVIDENCE_VIEW_JSON:\n", 1)[1].lstrip()
        )[0]
        findings = []
        for passage in view["passages"]:
            text = passage["text"]
            candidates = [text] if len(text) <= 500 else [text[:500], text[-500:]]
            quote = next(
                (q for q in candidates if q and text.find(q, text.find(q) + 1) < 0),
                None,
            )
            if quote:
                findings = [
                    {
                        "id": "finding-1",
                        "claim": quote,
                        "confidence": 0.9,
                        "supports": [{"ref": passage["ref"]}],
                    }
                ]
                break
        coverage = {
            "items": [
                {
                    "requirement_id": r["id"],
                    "status": "covered" if findings else "missing",
                    "reason": "scripted protocol coverage; not a semantic quality score",
                    "finding_ids": ["finding-1"] if findings else [],
                }
                for r in view["requirements"]
            ]
        }
        source_checks = [
            {
                "source": s["source"],
                "status": "eligible",
                "reason": "offline protocol fixture; not semantic validation",
            }
            for s in view["sources"]
        ]
        if "sufficient" in joined:
            return {
                "source_checks": source_checks,
                "findings": findings,
                "unresolved_gaps": [],
                "sufficient": bool(findings),
                "coverage": coverage,
            }
        action = "complete" if findings else "block"
        return {
            "action": action,
            "source_checks": source_checks,
            "coverage": coverage,
            "reason": "资料充足" if findings else "没有可用资料",
            "findings": findings,
            "unresolved_gaps": [],
        }

    # -- researcher loop -------------------------------------------------

    def _researcher(self, messages: list[Any]) -> AIMessage:
        query = self._branch_query(messages)
        if any(
            getattr(m, "type", None) == "human"
            and str(m.content).startswith("请继续收集证据并完成计划。")
            for m in messages
        ):
            # The deterministic adapter has no new source strategy after its
            # exhausted candidate list. Preserve no-source failure, not a loop.
            return AIMessage(content="当前脚本没有其他来源，保留未解决问题。")
        tool_messages = [
            text
            for message in messages
            if getattr(message, "type", None) == "tool"
            for text in [getattr(message, "content", "")]
        ]
        # Finish from the current read group, not a full-history cursor. This
        # deterministic adapter tests protocol only, never real answer quality.
        read = next(
            (
                p
                for p in reversed([_tool_payload(t) for t in tool_messages])
                if p and p.get("tool") == ToolName.READ_EVIDENCE.value and p.get("ok")
            ),
            None,
        )
        if read:
            preview = _tool_payload(read.get("preview")) or {}
            unit = next((p for p in preview.get("passages", []) if p.get("ref")), None)
            if unit:
                return self._tool_call(
                    [
                        (
                            "record_findings",
                            {
                                "findings": [
                                    {
                                        "claim": unit["text"],
                                        "refs": [unit["ref"]],
                                        "confidence": 0.9,
                                    }
                                ]
                            },
                        ),
                        (
                            WRITE_TODOS_TOOL,
                            {
                                "todos": [
                                    {
                                        "content": query[:200] or "研究",
                                        "status": "completed",
                                    }
                                ]
                            },
                        ),
                        (
                            "finish_research",
                            {"summary": "已记录当前原文支持；语义质量由独立评测判断。"},
                        ),
                    ]
                )
        search_results = [
            payload
            for payload in (_tool_payload(text) for text in tool_messages)
            if payload and payload.get("tool") == ToolName.SEARCH_WEB.value
        ]
        has_search = bool(search_results)
        todos_done = any(
            isinstance(payload.get("completed"), int)
            and isinstance(payload.get("total"), int)
            and payload["total"] > 0
            and payload["completed"] == payload["total"]
            for payload in (_tool_payload(text) for text in tool_messages)
            if payload and payload.get("tool") == WRITE_TODOS_TOOL
        )
        attempted = self._attempted_urls(messages)
        search_urls = self._search_urls(search_results)

        if not has_search:
            return self._tool_call(
                [
                    (
                        WRITE_TODOS_TOOL,
                        {
                            "todos": [
                                {
                                    "content": query[:200] or "研究",
                                    "status": "in_progress",
                                }
                            ]
                        },
                    ),
                    (ToolName.SEARCH_WEB.value, {"query": query, "limit": 5}),
                ]
            )

        candidates = [url for url in search_urls if url not in attempted]
        if len(attempted) < self._max_fetches and candidates:
            return self._tool_call(
                [(ToolName.FETCH_PAGE.value, {"url": candidates[0]})]
            )

        fetched_ids = list(
            dict.fromkeys(
                identity
                for payload in (_tool_payload(text) for text in tool_messages)
                if payload
                and payload.get("tool") == ToolName.FETCH_PAGE.value
                and payload.get("ok")
                for identity in payload.get("evidence_ids", [])
            )
        )
        attempted_reads = {
            call.get("args", {}).get("evidence_id")
            for m in messages
            for call in getattr(m, "tool_calls", None) or []
            if call.get("name") == ToolName.READ_EVIDENCE.value
        }
        unread = [
            identity for identity in fetched_ids if identity not in attempted_reads
        ]
        if unread:
            return self._tool_call(
                [
                    (
                        ToolName.READ_EVIDENCE.value,
                        {"evidence_id": unread[0], "query": query},
                    )
                ]
            )

        if not todos_done:
            return self._tool_call(
                [
                    (
                        WRITE_TODOS_TOOL,
                        {
                            "todos": [
                                {
                                    "content": query[:200] or "研究",
                                    "status": "completed",
                                }
                            ]
                        },
                    )
                ]
            )

        return AIMessage(content="研究结论：已基于抓取到的资料完成分析。")

    def _tool_call(self, calls: list[tuple[str, dict]]) -> AIMessage:
        tool_calls = []
        for name, args in calls:
            self._call_seq += 1
            tool_calls.append(
                {
                    "name": name,
                    "args": args,
                    "id": f"eval-call-{self._call_seq}",
                    "type": "tool_call",
                }
            )
        return AIMessage(content="", tool_calls=tool_calls)

    @staticmethod
    def _branch_query(messages: list[Any]) -> str:
        joined = "\n".join(str(getattr(message, "content", "")) for message in messages)
        match = re.search(r"当前研究分支：([^\n]+)", joined)
        if match:
            return match.group(1).strip()
        return _question(messages)

    @staticmethod
    def _attempted_urls(messages: list[Any]) -> set[str]:
        attempted: set[str] = set()
        for message in messages:
            if getattr(message, "type", None) != "ai":
                continue
            for call in getattr(message, "tool_calls", None) or []:
                if call.get("name") == ToolName.FETCH_PAGE.value:
                    url = (call.get("args") or {}).get("url")
                    if isinstance(url, str):
                        attempted.add(url)
        return attempted

    @staticmethod
    def _search_urls(search_results: list[dict[str, Any]]) -> list[str]:
        urls: list[str] = []
        for payload in search_results:
            preview = payload.get("preview")
            memory = payload.get("results")
            if isinstance(preview, str):
                try:
                    parsed = json.loads(preview)
                    memory = parsed.get("results") if isinstance(parsed, dict) else None
                except (TypeError, ValueError):
                    memory = None
            if not isinstance(memory, list):
                continue
            for item in memory:
                if not isinstance(item, dict):
                    continue
                url = item.get("url") or (item.get("result") or {}).get("url")
                if isinstance(url, str) and url not in urls:
                    urls.append(url)
        return urls


_DEFAULT_JUDGE = {
    "faithfulness": 4,
    "answer_correctness": 4,
    "source_coverage": 4,
    "citation_accuracy": 4,
    "coherence": 4,
}


class ScriptedJudgeModel:
    """Deterministic judge so the Tier 2 wiring can be tested offline."""

    def __init__(self, scores: dict[str, int] | None = None) -> None:
        self._scores = dict(scores or _DEFAULT_JUDGE)

    async def invoke(self, *, role: str, messages: list[Any], tools=None) -> str:
        _validate_envelope(messages)
        if role != "judge":
            raise ValueError(f"scripted judge only handles the judge role: {role}")
        return json.dumps(self._scores, ensure_ascii=False)
