"""Eval-only decision snapshots and a JSON boundary for isolated scoring."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess

from langchain_core.messages import AIMessage, ToolMessage


def _branch(role, messages) -> str:
    if role == "researcher":
        for message in messages:
            match = re.search(r"当前研究分支：([^\n]+)", str(message.content))
            if match:
                return match.group(1)
    return role


class TrajectoryRecorder:
    """Keep decisions and governed executions separate; never store model prose."""

    def __init__(self, *, record_content: bool = False) -> None:
        self._record_content = record_content
        self._messages: list[dict] = []
        self._results: list[dict] = []
        self._turns: list[dict] = []
        self._executions: list[dict] = []
        self._observations: dict[tuple[str, str], dict] = {}
        self._views: list[dict] = []
        self._agent_results: list[dict] = []

    def record_input(self, role, messages) -> int | None:
        if not self._record_content:
            return None
        self._messages.append(
            {
                "sequence": len(self._messages),
                "role": role,
                "branch": _branch(role, messages),
                "messages": [self._message(message) for message in messages],
                "response": None,
            }
        )
        return len(self._messages) - 1

    @staticmethod
    def _message(message) -> dict:
        payload = {
            "type": getattr(message, "type", "text"),
            "content": copy.deepcopy(getattr(message, "content", str(message))),
        }
        if isinstance(message, AIMessage):
            payload["tool_calls"] = copy.deepcopy(message.tool_calls)
        if isinstance(message, ToolMessage):
            payload["tool_call_id"] = message.tool_call_id
        return payload

    def record_observations(self, role, messages) -> None:
        branch = _branch(role, messages)
        for message in messages:
            if not isinstance(message, ToolMessage):
                continue
            try:
                payload = json.loads(message.content)
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            self._observations[(branch, message.tool_call_id)] = {
                "branch": branch,
                "tool_call_id": message.tool_call_id,
                **{
                    key: payload.get(key)
                    for key in ("tool", "ok", "error_code", "error_category")
                },
            }

    def record_model(self, role, messages, response, *, sequence=None) -> None:
        if sequence is not None:
            self._messages[sequence]["response"] = self._message(response)
        branch = _branch(role, messages)
        calls = response.tool_calls if isinstance(response, AIMessage) else []
        invalid = response.invalid_tool_calls if isinstance(response, AIMessage) else []
        self._turns.append(
            {
                "role": role,
                "branch": branch,
                "tool_calls": copy.deepcopy(calls),
                "invalid_tool_calls": [
                    {
                        "name": call.get("name"),
                        "args": str(call.get("args", ""))[:4000],
                        "id": call.get("id"),
                    }
                    for call in invalid
                ],
            }
        )

    def record_execution(self, caller, request, result=None, *, error=None) -> None:
        if self._record_content:
            self._results.append(
                {
                    "caller_id": caller.caller_id,
                    "call_id": request.call_id,
                    "result": result.model_dump(mode="json") if result else None,
                    "error_type": type(error).__name__ if error else None,
                }
            )
        self._executions.append(
            {
                "caller_id": caller.caller_id,
                "request_id": request.request_id,
                "call_id": request.call_id,
                "tool": request.tool.value,
                "arguments": copy.deepcopy(request.arguments),
                "ok": result.ok if result else False,
                "error_code": result.error_code if result else "tool_gateway_exception",
                "error_category": result.error_category.value
                if result and result.error_category
                else None,
                "cached": result.cached if result else False,
                "replayed": result.replayed if result else False,
                "exception_type": type(error).__name__ if error else None,
            }
        )

    def record_view(self, payload: dict) -> None:
        if len(self._views) >= 512:
            return
        view = {
            key: value[:128]
            for key in ("stage", "evidence_id", "content_hash", "passage_id")
            if isinstance((value := payload.get(key)), str)
        }
        view.update(
            {
                key: value
                for key in ("version", "start", "end", "attempt")
                if type(value := payload.get(key)) is int and value >= 0
            }
        )
        if type(payload.get("visibility")) is bool:
            view["visibility"] = payload["visibility"]
        self._views.append(view)

    def snapshot(self, *, full: bool = False) -> dict:
        payload = {
            "model_turns": self._turns,
            "tool_executions": self._executions,
            "tool_observations": list(self._observations.values()),
            "evidence_views": self._views,
        }
        if full:
            payload.update(
                model_messages=self._messages,
                tool_results=self._results,
                agent_tool_results=self._agent_results,
            )
        return copy.deepcopy(payload)

    def record_agent_result(self, payload: dict) -> None:
        if self._record_content:
            self._agent_results.append(copy.deepcopy(payload))


def _content_hash(value) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _git_identity() -> dict:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            ).stdout.strip()
        )
        return {"git_revision": revision, "git_dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"git_revision": None, "git_dirty": None}


def build_tool_eval_export(records, questions, corpus, *, model_kind: str) -> dict:
    by_id = {question.id: question for question in questions}
    samples = []
    for record in records:
        question = by_id[record.question_id]
        # Baseline requests are program-selected, not raw model tool decisions.
        references = (
            None if record.mode == "baseline" else question.reference_tool_calls
        )
        samples.append(
            {
                "question_id": record.question_id,
                "mode": record.mode,
                "run_id": record.run_id,
                "repeat_index": record.repeat_index,
                "question": record.question,
                "status": record.status,
                "termination_reason": record.termination_reason,
                "reference_tool_calls": None
                if references is None
                else [call.model_dump(mode="json") for call in references],
                "strict_tool_order": question.strict_tool_order,
                "trajectory": {
                    key: value
                    for key, value in record.trajectory.items()
                    if key
                    in {
                        "model_turns",
                        "tool_executions",
                        "tool_observations",
                        "evidence_views",
                    }
                },
            }
        )
    return {
        "schema_version": 1,
        "provenance": {
            "dataset_sha256": _content_hash(
                [question.model_dump(mode="json") for question in questions]
            ),
            "corpus_sha256": None
            if corpus is None
            else _content_hash(
                [doc.model_dump(mode="json") for doc in corpus.documents()]
            ),
            "model_kind": model_kind,
            "tools_backend": "live_web" if corpus is None else "frozen_local_corpus",
            **_git_identity(),
        },
        "samples": samples,
    }
