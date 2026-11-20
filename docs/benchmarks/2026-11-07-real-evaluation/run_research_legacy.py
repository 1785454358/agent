"""Bounded real-model experiment; run from backend. This makes paid requests."""

import asyncio
import os
from dataclasses import replace
from pathlib import Path

from deeptrace.config import Settings
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.eval.artifacts import ExperimentStore, atomic_json
from deeptrace.eval.assets import default_benchmark_path, load_benchmark
from deeptrace.eval.experiment import (
    EvaluationLimits, ModelIdentity, build_manifest,
    provider_endpoint_hash, provider_origin,
)
from deeptrace.eval.real import build_real_model_factory
from deeptrace.eval.report import render_markdown
from deeptrace.eval.runner import run_matrix
from deeptrace.eval.scoring import score_records
from deeptrace.eval.telemetry import RequestCounter
from deeptrace.eval.trajectory import build_tool_eval_export


async def execute(assets, factory, limits, store, model_counter):
    async def run_question(question):
        result = await run_matrix(
            [question], assets.corpus, model_factory=factory,
            modes=tuple(ResearchMode), run_prefix="real-dev-20261107",
            repeats=1, limits=limits, store=store,
            batch_model_counter=model_counter,
            response_mode=ResponseMode.ANSWER, include_baseline=True,
            response_max_content_chars=2500,
        )
        for row in result:
            print(f"{row.question_id} {row.mode}: {row.status}; "
                  f"models={row.model_calls}; seconds={row.wall_ms / 1000:.1f}", flush=True)
        return result

    # These four pilot trials are part of the 48 planned trials, not extra retries.
    first = await run_question(assets.questions[0])
    if all(row.status == "failed" for row in first):
        print("All pilot trials failed; stop before spending the remaining batch.", flush=True)
        return first
    semaphore = asyncio.Semaphore(3)

    async def bounded(question):
        async with semaphore:
            return await run_question(question)

    rest = await asyncio.gather(*(bounded(q) for q in assets.questions[1:]))
    return first + [r for rows in rest for r in rows]


def main():
    for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[key] = "false"
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    output = Path("../tmp/real-evaluation-20261107/research")
    assets = load_benchmark(default_benchmark_path(), split="dev")
    settings = replace(Settings.from_env(), openai_max_tokens=3072)
    if not settings.openai_api_key:
        raise ValueError("model credentials missing")
    limits = EvaluationLimits(
        max_model_calls=20, max_tool_calls=48, max_provider_attempts=30,
        max_batch_model_calls=600, max_batch_provider_attempts=900,
        run_timeout_seconds=240, agent_iterations=12,
    )
    manifest = build_manifest(
        assets.questions, assets.corpus,
        model=ModelIdentity(
            kind="real", name=settings.openai_model,
            provider=provider_origin(settings.openai_base_url),
            endpoint_sha256=provider_endpoint_hash(settings.openai_base_url),
            max_output_tokens=settings.openai_max_tokens,
            context_tokens=settings.model_context_tokens,
            request_timeout_seconds=settings.planner_timeout_seconds,
            thinking=settings.model_thinking, transport_attempts=1,
        ),
        modes=[m.value for m in ResearchMode] + ["baseline"], repeats=1,
        run_prefix="real-dev-20261107", limits=limits,
        response_mode="answer", response_max_content_chars=2500,
    )
    manifest["benchmark"] = {
        "dataset": assets.bundle.dataset, "identity_sha256": assets.identity,
        "split": "dev", "data_kind": assets.bundle.data_kind,
        "review_counts": assets.review_counts,
    }
    manifest["experiment_protocol"] = {
        "initial_pilot_questions": 1, "remaining_concurrent_questions": 3,
        "repeats": 1, "selection": "all 12 frozen dev questions; no test tuning",
        "scoring_provider_attempt_limits": {"ragas": 480, "claims": 800},
        "live_followup": "two separately reported live tasks, one workflow trial each",
    }
    with ExperimentStore(output, manifest) as store:
        providers = RequestCounter(900)
        models = RequestCounter(600)
        factory = build_real_model_factory(settings, limits=limits, batch_counter=providers)
        records = asyncio.run(execute(assets, factory, limits, store, models))
        by_id = {q.id: q for q in assets.questions}
        atomic_json(output / "records.json", [r.model_dump(mode="json") for r in records])
        atomic_json(output / "analysis-dev.json", assets.analysis_card())
        atomic_json(output / "quality_eval.json", {
            "schema_version": 2, "identity_sha256": store.identity, "manifest": manifest,
            "dataset_provenance": {**assets.review_counts, "limitations": assets.bundle.limitations},
            "samples": [{"record": r.model_dump(mode="json"),
                         "reference": by_id[r.question_id].model_dump(mode="json")} for r in records],
        })
        atomic_json(output / "tool_eval.json", build_tool_eval_export(
            records, assets.questions, assets.corpus, model_kind="real"))
        report = render_markdown(score_records(records, assets.questions))
        (output / "report.md").write_text(report, encoding="utf-8")
        print(report, flush=True)


if __name__ == "__main__":
    main()
