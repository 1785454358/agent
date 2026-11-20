"""One predeclared real-model validation per task; run from backend (paid)."""

import argparse
import asyncio
import hashlib
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


async def execute(questions, assets, modes, factory, limits, store, settings):
    models = RequestCounter(600)

    async def run_question(question):
        records = await run_matrix(
            [question], assets.corpus, model_factory=factory, modes=modes,
            run_prefix="answer-optimization-20261107", repeats=1, limits=limits,
            store=store, batch_model_counter=models,
            response_mode=ResponseMode.ANSWER, include_baseline=False,
            response_max_content_chars=2500, runtime_settings=settings,
        )
        for row in records:
            print(f"{row.question_id} {row.mode}: {row.status}; "
                  f"models={row.model_calls}; seconds={row.wall_ms / 1000:.1f}", flush=True)
        return records

    first = await run_question(questions[0])
    semaphore = asyncio.Semaphore(3)

    async def bounded(question):
        async with semaphore:
            return await run_question(question)

    rest = await asyncio.gather(*(bounded(q) for q in questions[1:]))
    return first + [r for rows in rest for r in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("workflow", "strategy-probes"), required=True)
    args = parser.parse_args()
    for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[key] = "false"
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    output = Path("../tmp/answer-optimization-20261107") / args.suite
    assets = load_benchmark(default_benchmark_path(), split="dev")
    questions = assets.questions
    modes = (ResearchMode.WORKFLOW,)
    if args.suite == "strategy-probes":
        selected = {"multi_hop-dev-01", "comparison-dev-01", "insufficient_evidence-dev-02"}
        questions = [q for q in questions if q.id in selected]
        modes = (ResearchMode.PLAN_EXECUTE, ResearchMode.MULTI_AGENT)
    settings = replace(Settings.from_env(), openai_max_tokens=3072)
    if not settings.openai_api_key:
        raise ValueError("model credentials missing")
    limits = EvaluationLimits(
        max_model_calls=20, max_tool_calls=48, max_provider_attempts=30,
        max_batch_model_calls=600, max_batch_provider_attempts=752,
        run_timeout_seconds=240, agent_iterations=12,
    )
    manifest = build_manifest(
        questions, assets.corpus,
        model=ModelIdentity(
            kind="real", name=settings.openai_model,
            provider=provider_origin(settings.openai_base_url),
            endpoint_sha256=provider_endpoint_hash(settings.openai_base_url),
            max_output_tokens=settings.openai_max_tokens,
            context_tokens=settings.model_context_tokens,
            request_timeout_seconds=settings.planner_timeout_seconds,
            thinking=settings.model_thinking, transport_attempts=1,
        ),
        modes=[m.value for m in modes], repeats=1,
        run_prefix="answer-optimization-20261107", limits=limits,
        response_mode="answer", response_max_content_chars=2500,
        runtime_settings=settings,
    )
    manifest["benchmark"] = {
        "dataset": assets.bundle.dataset, "identity_sha256": assets.identity,
        "split": "dev", "data_kind": assets.bundle.data_kind,
        "review_counts": assets.review_counts,
    }
    manifest["experiment_protocol"] = {
        "initial_pilot_questions": 1, "remaining_concurrent_questions": 3,
        "repeats": 1, "selection": [q.id for q in questions],
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scoring_provider_attempt_limits": {"ragas": 120, "claims": 200},
        "reviewer": "Agent; no human labels",
        "scope": "12 paired Workflow tasks; separate six alternate-strategy probes",
    }
    with ExperimentStore(output, manifest) as store:
        project = Path("..").resolve()
        for relative in manifest["source_files"]:
            target = output / "source_snapshot" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((project / relative).read_bytes())
        factory = build_real_model_factory(
            settings, limits=limits, batch_counter=RequestCounter(752))
        records = asyncio.run(execute(questions, assets, modes, factory, limits, store, settings))
        by_id = {q.id: q for q in questions}
        atomic_json(output / "records.json", [r.model_dump(mode="json") for r in records])
        atomic_json(output / "analysis-dev.json", assets.analysis_card())
        atomic_json(output / "quality_eval.json", {
            "schema_version": 2, "identity_sha256": store.identity, "manifest": manifest,
            "dataset_provenance": {**assets.review_counts, "limitations": assets.bundle.limitations},
            "samples": [{"record": r.model_dump(mode="json"),
                         "reference": by_id[r.question_id].model_dump(mode="json")} for r in records],
        })
        atomic_json(output / "tool_eval.json", build_tool_eval_export(
            records, questions, assets.corpus, model_kind="real"))
        report = render_markdown(score_records(records, questions))
        (output / "report.md").write_text(report, encoding="utf-8")
        print(report, flush=True)


if __name__ == "__main__":
    main()
