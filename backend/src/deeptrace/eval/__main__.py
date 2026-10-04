"""CLI: ``python -m deeptrace.eval`` runs the offline matrix and prints a report."""

from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.eval.artifacts import ExperimentStore, atomic_json
from deeptrace.eval.assets import load_benchmark
from deeptrace.eval.dataset import (
    default_corpus_path,
    default_dataset_path,
    load_corpus,
    load_questions,
)
from deeptrace.eval.env import Corpus
from deeptrace.eval.experiment import (
    EvaluationLimits,
    ModelIdentity,
    build_manifest,
    provider_endpoint_hash,
    provider_origin,
)
from deeptrace.eval.report import render_markdown
from deeptrace.eval.runner import run_matrix
from deeptrace.eval.scoring import score_records
from deeptrace.eval.scripted import ScriptedJudgeModel, ScriptedResearchModel
from deeptrace.eval.telemetry import RequestCounter
from deeptrace.eval.trajectory import build_tool_eval_export


def _parse_modes(value: str) -> tuple[ResearchMode, ...]:
    if not value.strip():
        return tuple(ResearchMode)
    return tuple(
        ResearchMode(part.strip()) for part in value.split(",") if part.strip()
    )


def _model_factories(
    model: str, judge: bool, *, settings=None, limits=None, batch_counter=None
):
    if model == "real":
        from deeptrace.eval.real import build_real_model_factory

        factory = build_real_model_factory(
            settings, limits=limits, batch_counter=batch_counter
        )
        return factory, None
    if model != "scripted":
        raise ValueError(f"unknown model: {model}")
    return ScriptedResearchModel, (ScriptedJudgeModel if judge else None)


def main(argv: list[str] | None = None, *, live_web: bool = False) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m deeptrace.eval",
        description="Run an offline or explicitly bounded real-model experiment.",
    )
    parser.add_argument("--corpus")
    parser.add_argument("--dataset")
    parser.add_argument(
        "--benchmark", type=Path, help="validated scoring-side benchmark bundle"
    )
    parser.add_argument(
        "--split", choices=["dev", "test"], help="benchmark split (default: dev)"
    )
    parser.add_argument(
        "--modes",
        default="plan_execute,workflow,multi_agent" if live_web else "",
        help="comma-separated subset: workflow,plan_execute,multi_agent",
    )
    parser.add_argument(
        "--model",
        default="real" if live_web else "scripted",
        choices=["scripted", "real"],
        help="scripted (offline) or real (OpenAI-compatible, needs credentials)",
    )
    parser.add_argument(
        "--repeats", type=int, default=1, help="repeat each (question, mode) k times"
    )
    parser.add_argument(
        "--judge", action="store_true", help="score results with an LLM-as-judge"
    )
    parser.add_argument("--run-prefix", default="eval")
    parser.add_argument(
        "--include-baseline",
        action="store_true",
        help="also run fixed search/fetch/answer with identical limits",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse completed/failed records with the exact same identity",
    )
    parser.add_argument("--max-model-calls", type=int, default=40)
    parser.add_argument("--max-tool-calls", type=int, default=24)
    parser.add_argument("--max-provider-attempts", type=int, default=80)
    parser.add_argument(
        "--max-batch-model-calls", type=int, default=120 if live_web else None
    )
    parser.add_argument(
        "--max-batch-provider-attempts", type=int, default=240 if live_web else None
    )
    parser.add_argument("--run-timeout", type=int, default=360 if live_web else 240)
    parser.add_argument("--agent-iterations", type=int, default=12)
    parser.add_argument(
        "--max-output-tokens", type=int, default=4096 if live_web else 2048
    )
    parser.add_argument(
        "--response-mode",
        choices=[m.value for m in ResponseMode],
        default="answer" if live_web else None,
    )
    parser.add_argument(
        "--response-max-chars",
        type=int,
        default=2000 if live_web else None,
        help="explicit shared answer length cap; "
        "does not guarantee provider token usage",
    )
    parser.add_argument(
        "--out",
        default="",
        help="directory to write report.md and records.json",
    )
    args = parser.parse_args(argv)

    if live_web and (
        args.corpus or args.benchmark or not args.dataset or args.model != "real"
    ):
        parser.error("live web requires --dataset, real model, and no corpus/benchmark")
    if live_web and (
        args.resume
        or args.include_baseline
        or (
            args.max_model_calls,
            args.max_tool_calls,
            args.max_provider_attempts,
            args.run_timeout,
            args.agent_iterations,
            args.max_output_tokens,
            args.response_mode,
            args.response_max_chars,
        )
        != (40, 24, 80, 360, 12, 4096, "answer", 2000)
    ):
        parser.error(
            "live evaluation requires registered per-run limits; no resume/baseline"
        )

    if args.benchmark and (args.dataset is not None or args.corpus is not None):
        parser.error("--benchmark cannot be mixed with --dataset or --corpus")
    if args.split and not args.benchmark:
        parser.error("--split requires --benchmark")

    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.resume and not args.out:
        parser.error("--resume requires --out")
    if args.model == "real":
        if (
            not args.out
            or args.max_batch_model_calls is None
            or args.max_batch_provider_attempts is None
        ):
            parser.error(
                "real experiments require --out and explicit "
                "batch model/provider ceilings"
            )
        if args.judge:
            parser.error(
                "real --judge is disabled: "
                "use the independent budgeted quality evaluator"
            )
    try:
        limits = EvaluationLimits(
            max_model_calls=args.max_model_calls,
            max_tool_calls=args.max_tool_calls,
            max_provider_attempts=args.max_provider_attempts,
            max_batch_model_calls=args.max_batch_model_calls,
            max_batch_provider_attempts=args.max_batch_provider_attempts,
            run_timeout_seconds=args.run_timeout,
            agent_iterations=args.agent_iterations,
        )
        if args.max_output_tokens < 1:
            raise ValueError("invalid output limit")
        if args.response_max_chars is not None and args.response_max_chars < 1:
            raise ValueError("invalid response character limit")
        modes = _parse_modes(args.modes)
    except ValueError:
        parser.error("invalid modes or resource ceilings")

    benchmark = None
    try:
        if args.benchmark:
            benchmark = load_benchmark(args.benchmark, split=args.split or "dev")
            questions, corpus = benchmark.questions, benchmark.corpus
        else:
            questions = load_questions(args.dataset or default_dataset_path())
            corpus = (
                None
                if live_web
                else Corpus(load_corpus(args.corpus or default_corpus_path()))
            )
    except (ValueError, OSError) as exc:
        parser.error(f"invalid evaluation assets: {type(exc).__name__}")
    settings = None
    identity = ModelIdentity(kind="scripted", name="scripted-research-v1")
    if args.model == "real":
        from deeptrace.config import Settings

        settings = replace(
            Settings.from_env(), openai_max_tokens=args.max_output_tokens
        )
        if not settings.openai_api_key:
            parser.error("real model credentials are missing")
        identity = ModelIdentity(
            kind="real",
            name=settings.openai_model,
            provider=provider_origin(settings.openai_base_url),
            endpoint_sha256=provider_endpoint_hash(settings.openai_base_url),
            max_output_tokens=settings.openai_max_tokens,
            context_tokens=settings.model_context_tokens,
            request_timeout_seconds=settings.planner_timeout_seconds,
        )
    live_identity, live_factory = None, None
    if live_web:
        from deeptrace.eval.live import environment_factory, retrieval_identity

        live_identity = retrieval_identity(settings)
        live_factory = environment_factory(settings)
    manifest = build_manifest(
        questions,
        corpus,
        model=identity,
        modes=[m.value for m in modes]
        + (["baseline"] if args.include_baseline else []),
        repeats=args.repeats,
        run_prefix=args.run_prefix,
        limits=limits,
        response_mode=args.response_mode,
        response_max_content_chars=args.response_max_chars,
        live_retrieval=live_identity,
    )
    # Legacy scripted judge participates in identity; do not resume unjudged data.
    manifest["judge_kind"] = "legacy_scripted" if args.judge else None
    if benchmark:
        manifest["benchmark"] = {
            "dataset": benchmark.bundle.dataset,
            "identity_sha256": benchmark.identity,
            "split": benchmark.split,
            "data_kind": benchmark.bundle.data_kind,
            "review_counts": benchmark.review_counts,
        }
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    output = Path(args.out) if args.out else None
    try:
        with (
            ExperimentStore(output, manifest, resume=args.resume)
            if output
            else nullcontext(None) as store
        ):
            saved = (
                [store.load(run_id) for run_id in manifest["sample_ids"]]
                if store
                else []
            )
            prior = [r.get("usage", {}).get("provider_attempts") for r in saved if r]
            if args.model == "real" and any(type(n) is not int or n < 0 for n in prior):
                raise ValueError("resume requires known provider attempt counts")
            previous_attempts = sum(n for n in prior if n is not None)
            batch_counter = (
                RequestCounter(
                    limits.max_batch_provider_attempts, used=previous_attempts
                )
                if limits.max_batch_provider_attempts
                else None
            )
            model_factory, judge_factory = _model_factories(
                args.model,
                args.judge,
                settings=settings,
                limits=limits,
                batch_counter=batch_counter,
            )
            records = asyncio.run(
                run_matrix(
                    questions,
                    corpus,
                    model_factory=model_factory,
                    modes=modes,
                    run_prefix=args.run_prefix,
                    repeats=args.repeats,
                    judge_factory=judge_factory,
                    limits=limits,
                    store=store,
                    response_mode=ResponseMode(args.response_mode)
                    if args.response_mode
                    else None,
                    include_baseline=args.include_baseline,
                    response_max_content_chars=args.response_max_chars,
                    environment_factory=live_factory,
                )
            )
            if output:
                atomic_json(
                    output / "records.json",
                    [r.model_dump(mode="json") for r in records],
                )
                atomic_json(
                    output / "tool_eval.json",
                    build_tool_eval_export(
                        records, questions, corpus, model_kind=args.model
                    ),
                )
                by_id = {q.id: q for q in questions}
                atomic_json(
                    output / "quality_eval.json",
                    {
                        "schema_version": 2,
                        "identity_sha256": store.identity,
                        "manifest": manifest,
                        **(
                            {
                                "dataset_provenance": {
                                    **benchmark.review_counts,
                                    "benchmark_identity": benchmark.identity,
                                    "limitations": benchmark.bundle.limitations,
                                }
                            }
                            if benchmark
                            else {}
                        ),
                        "samples": [
                            {
                                "record": r.model_dump(mode="json"),
                                "reference": by_id[r.question_id].model_dump(
                                    mode="json"
                                ),
                            }
                            for r in records
                        ],
                    },
                )
                report = score_records(records, questions)
                (output / "report.md").write_text(
                    render_markdown(report, tools_backend=manifest["tools_backend"]),
                    encoding="utf-8",
                )
    except ValueError as exc:
        parser.error(str(exc))
    report = score_records(records, questions)
    markdown = render_markdown(report, tools_backend=manifest["tools_backend"])
    print(markdown)

    return int(
        any(
            record.status != "completed" or record.judge_error or record.artifact_errors
            for record in records
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
