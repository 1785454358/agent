"""Replay 12 historical valid reviews, then repair one historical error live.

Historical outputs are explicitly replayed, not new Provider calls. Only the
corrective request is live. This is a protocol fault-injection probe, not a
fresh Agent trial or evidence of higher factual accuracy.
"""

import asyncio
import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import replace
from pathlib import Path

from langchain_core.messages import AIMessage

from deeptrace.config import Settings
from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.assets import default_benchmark_path, load_benchmark
from deeptrace.eval.env import build_eval_context
from deeptrace.eval.experiment import source_identity
from deeptrace.eval.telemetry import RequestCounter
from deeptrace.eval.trajectory import _content_hash
from deeptrace.eval.writer_benchmark import probe_gateway
from deeptrace.responses.citations import extract_citation_markers
from deeptrace.responses.fact_review import (
    ReviewedAnswer,
    review_answer,
    review_messages,
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def saved_review(record):
    return [t for t in record["trajectory"]["model_messages"] if t["role"] == "responder"
        and any("ANSWER_REVIEW_JSON:\n" in str(m.get("content", "")) for m in t["messages"])][-1]


async def main():
    project = Path("..").resolve()
    root = project / "tmp/answer-review-boundary-20261108"
    output = root / "recovery-verification"
    if output.exists() and any(output.iterdir()):
        raise ValueError("verification output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    parent = read(project / "tmp/harness-contract-20261107/baseline/quality_eval.json")
    spec = importlib.util.spec_from_file_location("before_recovery", root /
        "before/backend/src/deeptrace/responses/fact_review.py")
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    spec.loader.exec_module(original)
    assets = load_benchmark(default_benchmark_path(), split="dev")
    checks = []
    for sample in parent["samples"]:
        row = sample["record"]
        turn = saved_review(row)
        data = json.loads(turn["messages"][-1]["content"].split("ANSWER_REVIEW_JSON:\n", 1)[1])
        cap = int(re.findall(r"不超过(\d+)字符", turn["messages"][0]["content"])[-1])
        args = dict(question=row["question"], constraints=[], content=data["draft"],
                    sources=data["original_passages"], requirements=data["answer_requirements"],
                    max_content_chars=cap)
        messages = review_messages(**args)
        assert [m.content for m in messages] == [m.content for m in original.review_messages(**args)]
        assert [m.content for m in messages] == [m["content"] for m in turn["messages"]]

        class HistoricalGateway:
            def __init__(self):
                self.calls = 0

            async def invoke(self, *, messages, **kwargs):
                self.calls += 1
                assert self.calls == 1
                assert [m.content for m in messages] == [m["content"] for m in turn["messages"]]
                return AIMessage(content=turn["response"]["content"])

        gateway = HistoricalGateway()
        env = build_eval_context(assets.corpus, model_gateway=gateway, memory_enabled=False,
                                 run_id=f"historical-valid-{row['question_id']}")
        try:
            reviewed = await review_answer(env.context, **args, input_budget=120000)
            assert reviewed.model_dump() == ReviewedAnswer.model_validate_json(turn["response"]["content"]).model_dump()
            checks.append({"question_id": row["question_id"], "first_request_byte_identical": True,
                           "review_unchanged": True, "replayed_calls": gateway.calls,
                           "new_provider_attempts": 0})
        finally:
            await env.aclose()
    atomic_json(output / "historical-valid-replays.json", checks)

    qid = "version_boundary-dev-02"
    old_error = next(r for r in read(root / "replay-request-bound/records.json") if r["question_id"] == qid)
    error_text = old_error["trajectory"]["model_messages"][0]["response"]["content"]
    assert "[4]" in json.loads(error_text)["content"]
    material = next(m for m in read(root / "replay-request-bound/materials.json") if m["question_id"] == qid)
    assert material["allowed_markers"] == ["[1]"]
    settings = replace(Settings.from_env(), openai_max_tokens=3072)
    live, telemetry = probe_gateway(settings, RequestCounter(1), max_calls=1)
    requests = []

    class HistoricalErrorThenLive:
        async def invoke(self, *, messages, **kwargs):
            requests.append([str(m.content) for m in messages])
            if len(requests) == 1:
                return AIMessage(content=error_text)
            assert len(requests) == 2
            return await live.invoke(messages=messages, **kwargs)

    env = build_eval_context(assets.corpus, model_gateway=HistoricalErrorThenLive(), memory_enabled=False,
                             run_id="historical-error-live-repair")
    try:
        reviewed = await review_answer(
            env.context, question=material["question"], constraints=[], content=material["draft"],
            sources=material["sources"], requirements=material["requirements"],
            max_content_chars=material["cap"], input_budget=120000)
        assert set(extract_citation_markers(reviewed.content)) == {"[1]"}
        assert len(requests) == 2
        assert requests[0][-1] == requests[1][-1]
        report = {"kind": "historical protocol-error injection plus one live corrective call",
            "question_id": qid, "historical_response_sha256": _content_hash(error_text),
            "original_failed_run_id": old_error["run_id"], "replayed_first_response": error_text,
            "historical_first_response_provider_attempts": 0, "actual_repair_provider_attempts": 1,
            "requests": requests, "live_gateway_calls": live.calls, "usage": telemetry.snapshot(),
            "review": reviewed.model_dump(mode="json"), "same_human_payload": True,
            "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_files": source_identity(project),
            "limitations": "Not a fresh two-call Agent trial; no factual-quality improvement claim."}
        atomic_json(output / "live-repair.json", report)
    finally:
        await env.aclose()
    print("12 historical valid reviews unchanged; one historical citation error repaired by one live Provider call.")


if __name__ == "__main__":
    asyncio.run(main())
