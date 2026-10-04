"""Budgeted Ragas 0.4.3 quality scorer; isolated from the production SDK.

Outcome-only goal view, actual selected evidence for faithfulness, full gold on
the scoring side only. No automatic rerun of interrupted metrics or Agent runs.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import tempfile
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

os.environ["RAGAS_DO_NOT_TRACK"] = "true"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

METRICS = ("faithfulness", "factual_correctness", "agent_goal_accuracy")
ADAPTER_VERSION = "quality-v2-metric-specific-input-limits"


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            name = handle.name
            json.dump(
                value, handle, ensure_ascii=False, sort_keys=True, allow_nan=False
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


class AttemptLedger:
    """Counts each SDK-facing attempt, including Instructor validation retries."""

    def __init__(self, path, limit):
        if type(limit) is not int or limit < 1:
            raise ValueError("positive attempt limit required")
        self.path = Path(path)
        self.limit = limit
        self.lock = asyncio.Lock()
        if self.path.is_symlink():
            raise ValueError("symlink ledger refused")
        self.attempts = (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path.exists()
            else []
        )
        if not isinstance(self.attempts, list) or len(self.attempts) > limit:
            raise ValueError("invalid prior attempt ledger")
        for entry in self.attempts:
            if not isinstance(entry, dict) or entry.get("status") not in {
                "in_flight",
                "ok",
                "error",
                "cancelled",
            }:
                raise ValueError("invalid attempt record")
            for key in ("input_tokens", "output_tokens"):
                count = entry.get(key)
                if count is not None and (type(count) is not int or count < 0):
                    raise ValueError("invalid usage record")

    async def invoke(self, raw, **kwargs):
        async with self.lock:
            if len(self.attempts) >= self.limit:
                raise RuntimeError("judge_provider_attempt_budget_exhausted")
            messages = kwargs.get("messages", [])
            if len(json.dumps(messages)) > 800_000:
                raise ValueError("judge_prompt_size_limit")
            entry = {
                "status": "in_flight",
                "input_tokens": None,
                "output_tokens": None,
                "model": kwargs.get("model"),
                "messages": messages,
                "response": None,
            }
            self.attempts.append(entry)
            atomic_json(self.path, self.attempts)
        try:
            result = await raw(**kwargs)
        except BaseException as exc:
            entry.update(
                status="cancelled"
                if isinstance(exc, asyncio.CancelledError)
                else "error",
                error=type(exc).__name__,
            )
            atomic_json(self.path, self.attempts)
            raise
        usage = getattr(result, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        valid = all(type(n) is int and n >= 0 for n in (input_tokens, output_tokens))
        entry.update(
            status="ok",
            input_tokens=input_tokens if valid else None,
            output_tokens=output_tokens if valid else None,
        )
        choices = getattr(result, "choices", [])
        content = (
            getattr(getattr(choices[0], "message", None), "content", None)
            if choices
            else None
        )
        if isinstance(content, str) and len(content) <= 100_000:
            entry["response"] = content
        atomic_json(self.path, self.attempts)
        return result

    def snapshot(self):
        measured = [
            a
            for a in self.attempts
            if a["input_tokens"] is not None and a["output_tokens"] is not None
        ]
        missing = len(self.attempts) - len(measured)
        return {
            "provider_attempts": len(self.attempts),
            "max_provider_attempts": self.limit,
            "measured_usage_attempts": len(measured),
            "missing_usage_attempts": missing,
            "observed_input_tokens": sum(a["input_tokens"] for a in measured),
            "observed_output_tokens": sum(a["output_tokens"] for a in measured),
            "input_tokens": None
            if missing
            else sum(a["input_tokens"] for a in measured),
            "output_tokens": None
            if missing
            else sum(a["output_tokens"] for a in measured),
            "cost": None,
        }


def cache_key(sample, metric, judge_identity):
    # Include source and every scoring input; no cache across changed prompts/deps.
    return digest(
        {
            "sample": sample,
            "metric": metric,
            "judge": judge_identity,
            "adapter": ADAPTER_VERSION,
            "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
    )


def unmeasured(status, reason):
    return {"status": status, "value": None, "reason": reason}


async def score_metric(sample, name, llm):
    if version("ragas") != "0.4.3":
        raise RuntimeError("Ragas 0.4.3 required")
    if name not in METRICS:
        raise ValueError("unknown metric")
    record, reference = sample["record"], sample["reference"]
    answer, question, gold = (
        record.get("answer", ""),
        record.get("question", ""),
        reference.get("gold_answer", ""),
    )
    if not answer.strip() or not question.strip():
        return unmeasured("not_applicable", "missing_question_or_answer")
    contexts = [
        e["body"]
        for e in record.get("evidence", [])
        if e.get("selected_for_outcome")
        and isinstance(e.get("body"), str)
        and e["body"].strip()
    ]
    if name == "faithfulness" and (not contexts or record.get("artifact_errors")):
        return unmeasured("not_applicable", "missing_or_incomplete_selected_evidence")
    if name != "faithfulness" and not gold.strip():
        return unmeasured("not_applicable", "missing_reference")
    # Never silently truncate quality inputs. Large samples need explicit policy.
    if name == "faithfulness":
        metric_inputs = [answer, question, *contexts]
    elif name == "factual_correctness":
        metric_inputs = [answer, gold]
    else:
        metric_inputs = [answer, question, gold]
    if sum(map(len, metric_inputs)) > 100_000:
        return unmeasured("not_applicable", "quality_input_size_limit")
    from ragas.messages import AIMessage, HumanMessage
    from ragas.metrics.collections import (
        AgentGoalAccuracy,
        FactualCorrectness,
        Faithfulness,
    )

    try:
        async with asyncio.timeout(120):
            if name == "faithfulness":
                result = await Faithfulness(llm=llm).ascore(
                    user_input=question, response=answer, retrieved_contexts=contexts
                )
            elif name == "factual_correctness":
                result = await FactualCorrectness(llm=llm, mode="f1").ascore(
                    response=answer, reference=gold
                )
            else:
                # This is deliberately NOT a fabricated cross-branch tool conversation.
                result = await AgentGoalAccuracy(llm=llm).ascore(
                    user_input=[
                        HumanMessage(content=question),
                        AIMessage(content=answer),
                    ],
                    reference=gold,
                )
        value = float(result.value)
        if not math.isfinite(value) or not 0 <= value <= 1:
            return unmeasured("error", "invalid_metric_value")
        return {"status": "ok", "value": value, "reason": None}
    except Exception as exc:  # noqa: BLE001 — scoring failures are retained, not zero
        return unmeasured("error", type(exc).__name__)


def validate_export(payload):
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 2:
        raise ValueError("quality export schema 2 required")
    if not isinstance(payload.get("samples"), list) or not payload["samples"]:
        raise ValueError("nonempty quality samples required")
    if not isinstance(payload.get("manifest"), dict) or digest(
        payload["manifest"]
    ) != payload.get("identity_sha256"):
        raise ValueError("experiment manifest integrity mismatch")
    seen = set()
    for sample in payload["samples"]:
        record, reference = sample["record"], sample["reference"]
        if (
            record["question_id"] != reference["id"]
            or record["question"] != reference["question"]
        ):
            raise ValueError("reference question mismatch")
        if record["run_id"] in seen or record["status"] not in {
            "completed",
            "partial",
            "failed",
        }:
            raise ValueError("invalid or duplicate run")
        seen.add(record["run_id"])


async def evaluate(payload, output, judge, credentials, max_attempts):
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    ledger = AttemptLedger(output / "attempts.json", max_attempts)
    async with AsyncOpenAI(
        api_key=credentials["key"],
        base_url=credentials["url"],
        max_retries=0,
        timeout=60,
    ) as client:
        raw = client.chat.completions.create

        async def metered(**kwargs):
            return await ledger.invoke(raw, **kwargs)

        client.chat.completions.create = metered
        # Instructor retries are explicitly one attempt per structured generation;
        # ledger still guards every create call, not just each top-level metric.
        llm = llm_factory(
            judge["model"],
            provider="openai",
            adapter="instructor",
            client=client,
            temperature=0,
            max_tokens=2048,
            max_retries=1,
        )
        results = []
        for sample in payload["samples"]:
            row = {
                "run_id": sample["record"]["run_id"],
                "question_id": sample["record"]["question_id"],
                "mode": sample["record"]["mode"],
                "system_status": sample["record"]["status"],
                "metrics": {},
            }
            for name in METRICS:
                key = cache_key(sample, name, judge)
                target, claim = output / f"{key}.json", output / f"{key}.claim"
                if target.exists():
                    saved = json.loads(target.read_text(encoding="utf-8"))
                    if saved["key"] != key or saved["result_sha256"] != digest(
                        saved["result"]
                    ):
                        raise ValueError("quality cache integrity mismatch")
                    result = saved["result"]
                else:
                    if claim.exists():
                        raise ValueError(
                            "interrupted quality metric requires manual inspection"
                        )
                    claim.touch(exist_ok=False)
                    result = await score_metric(sample, name, llm)
                    atomic_json(
                        target,
                        {"key": key, "result": result, "result_sha256": digest(result)},
                    )
                    claim.unlink()
                row["metrics"][name] = result
                # Persist each finished score; later judge failure cannot lose it.
                atomic_json(
                    output / "progress.json",
                    {"completed": results, "current": row, "usage": ledger.snapshot()},
                )
            results.append(row)
        report = {
            "schema_version": 1,
            "experiment_identity": payload["identity_sha256"],
            "judge": judge,
            "goal_view": "question_and_final_answer_only",
            "results": results,
            "usage": ledger.snapshot(),
            "human_review": None,
        }
        atomic_json(output / "quality_scores.json", report)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-provider-attempts", required=True, type=int)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--judge-model")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.max_provider_attempts < 1:
        parser.error("positive judge limit required")
    input_path = Path(args.input)
    if input_path.stat().st_size > 64 * 1024 * 1024:
        parser.error("quality export exceeds 64 MiB")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    validate_export(payload)
    if version("ragas") != "0.4.3":
        parser.error("run in pinned .venv-ragas")
    from dotenv import dotenv_values

    config = {**dotenv_values(args.env_file), **os.environ}
    key, url = config.get("OPENAI_API_KEY"), config.get("OPENAI_BASE_URL")
    model = args.judge_model or config.get("OPENAI_MODEL")
    if not key or not url or not model:
        parser.error("judge credentials, base URL and model required")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        parser.error("credential-free HTTP(S) endpoint required")
    judge = {
        "model": model,
        "provider": f"{parsed.scheme}://{parsed.netloc}",
        "endpoint_sha256": digest(url.rstrip("/")),
        "temperature": 0,
        "max_tokens": 2048,
        "sdk_retries": 0,
        "instructor_attempts": 1,
        "same_model_as_agent": model == payload["manifest"]["model"]["name"],
        "ragas": version("ragas"),
        "openai": version("openai"),
        "instructor": version("instructor"),
        "adapter": ADAPTER_VERSION,
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    identity = {
        "input_sha256": digest(payload),
        "judge": judge,
        "max_provider_attempts": args.max_provider_attempts,
    }
    output = Path(args.out)
    if output.is_symlink() or any(p.is_symlink() for p in output.absolute().parents):
        parser.error("symlink output refused")
    output = output.resolve()
    if args.resume:
        if (
            not (output / "identity.json").exists()
            or json.loads((output / "identity.json").read_text(encoding="utf-8"))
            != identity
        ):
            parser.error("quality identity mismatch")
    elif output.exists() and any(output.iterdir()):
        parser.error("nonempty quality directory refused")
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".writer.lock"
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
    except FileExistsError:
        parser.error("quality writer lock exists; inspect before recovery")
    try:
        if not args.resume:
            atomic_json(output / "identity.json", identity)
        report = asyncio.run(
            evaluate(
                payload,
                output,
                judge,
                {"key": key, "url": url},
                args.max_provider_attempts,
            )
        )
    except Exception as exc:  # noqa: BLE001 — never print raw provider exception text
        print(json.dumps({"status": "error", "error": type(exc).__name__}))
        return 1
    finally:
        lock.unlink()
    # Only bounded, credential-free summary printed, not prompts or exceptions.
    print(
        json.dumps(
            {"results": report["results"], "usage": report["usage"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return int(
        any(
            m["status"] == "error"
            for r in report["results"]
            for m in r["metrics"].values()
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
