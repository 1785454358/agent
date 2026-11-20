"""One paid final-review call per saved draft; not an end-to-end research run.

Run from backend. No benchmark gold/reference answer reaches generation.
"""

import asyncio
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from deeptrace.config import Settings
from deeptrace.domain import ResponseMode
from deeptrace.eval.artifacts import ExperimentStore, atomic_json
from deeptrace.eval.assets import default_benchmark_path, load_benchmark
from deeptrace.eval.env import build_eval_context
from deeptrace.eval.experiment import (
    EvaluationLimits,
    ModelIdentity,
    build_manifest,
    provider_endpoint_hash,
    provider_origin,
)
from deeptrace.eval.runner import RunRecord
from deeptrace.eval.telemetry import RequestCounter
from deeptrace.eval.trajectory import _content_hash
from deeptrace.eval.writer_benchmark import probe_gateway
from deeptrace.responses.citations import extract_citation_markers, validate_citations
from deeptrace.responses.fact_review import review_answer
from deeptrace.responses.graph import _looks_incomplete
from deeptrace.responses.models import ResponseDraft


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(parent, original):
    materials = []
    for sample in parent["samples"]:
        record = sample["record"]
        turns = [t for t in record["trajectory"]["model_messages"]
                 if t["role"] == "responder" and any("ANSWER_REVIEW_JSON:\n" in str(m.get("content", ""))
                                                     for m in t["messages"])]
        turn = turns[-1]
        data = json.loads(turn["messages"][-1]["content"].split("ANSWER_REVIEW_JSON:\n", 1)[1])
        cap = int(re.findall(r"不超过(\d+)字符", turn["messages"][0]["content"])[-1])
        assert cap <= 2500
        messages = original.review_messages(
            question=record["question"], constraints=[], content=data["draft"],
            sources=data["original_passages"], requirements=data["answer_requirements"],
            max_content_chars=cap)
        assert [m.content for m in messages] == [m["content"] for m in turn["messages"]]
        parsed = [re.match(r"^\[(\d+)\] id=(\S+)", source) for source in data["original_passages"]]
        assert all(parsed)
        mapping = {int(m[1]): m[2] for m in parsed}
        selected = {e["id"] for e in record["evidence"] if e["selected_for_outcome"]}
        assert set(mapping.values()) <= selected
        ids = [e["id"] for e in record["evidence"]]
        spare = iter(e for e in ids if e not in mapping.values())
        loaded = [mapping[i] if i in mapping else next(spare) for i in range(1, max(mapping) + 1)]
        materials.append({"question_id": record["question_id"], "question": record["question"],
                          "draft": data["draft"], "sources": data["original_passages"],
                          "requirements": data["answer_requirements"], "cap": cap,
                          "loaded_ids": loaded, "visible_ids": list(mapping.values()),
                          "allowed_markers": [f"[{i}]" for i in mapping],
                          "parent_run_id": record["run_id"], "parent_record_sha256": _content_hash(record)})
    return materials


async def execute(assets, parent, materials, settings, output, store):
    shared = RequestCounter(12)
    records, reviews = [], []
    by_question = {s["record"]["question_id"]: s for s in parent["samples"]}
    for material in materials:
        qid = material["question_id"]
        run_id = f"source-first-replay-20261108-{qid}-workflow"
        store.claim(run_id)
        gateway, telemetry = probe_gateway(settings, shared, max_calls=1)
        env = build_eval_context(assets.corpus, model_gateway=gateway,
                                 run_id=run_id, memory_enabled=False)
        row = copy.deepcopy(by_question[qid]["record"])
        row.update(run_id=run_id, status="failed", termination_reason="final_review_replay_failed",
                   response_partial_reason=None, answered=False, answer="", cited_evidence_ids=[],
                   artifact_errors=[], executed_steps=1, model_calls=0, tool_calls=0,
                   fetched_pages=0, tool_retries=0, judge=None, judge_attempted=False,
                   judge_error=None, system_error=None, unresolved_gaps=[], trajectory={})
        started = perf_counter()
        detail = {"question_id": qid, "material_sha256": _content_hash(material), "error": None}
        try:
            reviewed = await review_answer(
                env.context, question=material["question"], constraints=[],
                content=material["draft"], sources=material["sources"],
                requirements=material["requirements"], response_mode=ResponseMode.ANSWER,
                max_content_chars=material["cap"],
                input_budget=settings.model_context_tokens - settings.context_safety_tokens - 3072)
            if _looks_incomplete(reviewed.content):
                raise ValueError("incomplete_reviewed_answer")
            if not set(extract_citation_markers(reviewed.content)) <= set(material["allowed_markers"]):
                raise ValueError("invalid_reviewed_citation")
            outcome = validate_citations(
                ResponseDraft(response_mode=ResponseMode.ANSWER, content=reviewed.content),
                loaded_evidence_ids=material["loaded_ids"], visible_evidence_ids=material["visible_ids"])
            if not outcome.cited_evidence_ids:
                raise ValueError("no_supported_citations")
            partial = "answer_review_incomplete" if reviewed.unanswered_points else None
            row.update(status="partial" if partial else "completed", answered=not bool(partial),
                       answer=outcome.content, cited_evidence_ids=outcome.cited_evidence_ids,
                       response_partial_reason=partial, termination_reason=partial or "final_review_replay_completed",
                       unresolved_gaps=reviewed.unanswered_points)
            detail["review"] = reviewed.model_dump(mode="json")
        except Exception as exc:
            row["system_error"] = detail["error"] = type(exc).__name__
        finally:
            row["usage"] = telemetry.snapshot()
            row["model_calls"] = len(gateway.calls)
            row["wall_ms"] = (perf_counter() - started) * 1000
            row["trajectory"] = {"model_messages": [{
                "role": call["role"], "branch": "final_review_replay", "sequence": i,
                "messages": [{"type": typ, "content": text} for typ, text in zip(
                    ("system", "human"), call["messages"], strict=True)],
                "response": {"type": "ai", "content": call.get("response", "")},
            } for i, call in enumerate(gateway.calls)],
                "tool_executions": [], "model_turns": []}
            row = RunRecord.model_validate(row).model_dump(mode="json")
            store.save(row)
            records.append(row)
            reviews.append(detail)
            atomic_json(output / "reviews.json", reviews)
            await env.aclose()
        print(f"{qid}: {row['status']}; new provider attempts={row['usage']['provider_attempts']}; "
              f"chars={len(row['answer'])}", flush=True)
    return records


def main():
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    root = Path("..").resolve()
    output = root / "tmp/answer-review-boundary-20261108/replay-source-first"
    parent_path = root / "tmp/harness-contract-20261107/baseline/quality_eval.json"
    parent = read(parent_path)
    spec = importlib.util.spec_from_file_location("original_answer_reviewer", root /
        "tmp/answer-review-boundary-20261108/before/backend/src/deeptrace/responses/fact_review.py")
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    spec.loader.exec_module(original)
    materials = prepare(parent, original)
    assert len(materials) == 12
    assets = load_benchmark(default_benchmark_path(), split="dev")
    settings = replace(Settings.from_env(), openai_max_tokens=3072)
    assert settings.openai_model == parent["manifest"]["model"]["name"]
    assert settings.model_thinking == parent["manifest"]["model"]["thinking"]
    assert provider_endpoint_hash(settings.openai_base_url) == parent["manifest"]["model"]["endpoint_sha256"]
    limits = EvaluationLimits(max_model_calls=1, max_tool_calls=1, max_provider_attempts=1,
                              max_batch_model_calls=12, max_batch_provider_attempts=12,
                              run_timeout_seconds=90, agent_iterations=1)
    manifest = build_manifest(
        assets.questions, assets.corpus, model=ModelIdentity(
            kind="real", name=settings.openai_model, provider=provider_origin(settings.openai_base_url),
            endpoint_sha256=provider_endpoint_hash(settings.openai_base_url), max_output_tokens=3072,
            context_tokens=settings.model_context_tokens, request_timeout_seconds=settings.planner_timeout_seconds,
            thinking=settings.model_thinking, transport_attempts=1),
        modes=["workflow"], repeats=1, run_prefix="source-first-replay-20261108", limits=limits,
        response_mode="answer", response_max_content_chars=2500, runtime_settings=settings)
    manifest["execution_profile"] = {"executor": "final_review_replay", "parent_identity": parent["identity_sha256"],
                                      "materials_sha256": _content_hash(materials), "new_calls_per_task": 1}
    manifest["experiment_protocol"] = {"kind": "fixed-visible-passages-source-first-completion",
        "parent_input_sha256": _content_hash(parent), "parent_input_file_sha256": hashlib.sha256(parent_path.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "selection": "all 12 frozen dev questions; draft deliberately excluded from model input; same visible passages; no retries",
        "limitations": "component-only comparison; not a complete Agent trial or full-run gate input"}
    manifest["benchmark"] = parent["manifest"]["benchmark"]
    with ExperimentStore(output, manifest) as store:
        for rel in manifest["source_files"]:
            p = output / "source_snapshot" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((root / rel).read_bytes())
        atomic_json(output / "materials.json", materials)
        records = asyncio.run(execute(assets, parent, materials, settings, output, store))
        atomic_json(output / "records.json", records)
        by_id = {s["record"]["question_id"]: s["reference"] for s in parent["samples"]}
        atomic_json(output / "quality_eval.json", {"schema_version": 2, "identity_sha256": store.identity,
            "manifest": manifest, "dataset_provenance": parent["dataset_provenance"],
            "samples": [{"record": row, "reference": by_id[row["question_id"]]} for row in records]})
        atomic_json(output / "analysis-dev.json", read(parent_path.parent / "analysis-dev.json"))


if __name__ == "__main__":
    main()
