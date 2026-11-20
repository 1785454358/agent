"""python -m deeptrace.evaluation --help"""
import argparse
import asyncio
import subprocess
import json
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client, aevaluate, tracing_context

from .datasets import load_examples, sync_dataset

DATA_DIR = Path(__file__).parent / 'data'
DEFAULT_DATASET = 'deeptrace-grounded-v1'


def parser():
    cli = argparse.ArgumentParser(description="LangSmith datasets and production-runtime experiments")
    commands = cli.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync-dataset")
    sync.add_argument("--file", type=Path, default=DATA_DIR / "research-v1.jsonl")
    sync.add_argument("--dataset", default=DEFAULT_DATASET)
    sync.add_argument("--corpus", type=Path, help="Native source documents to attach to every example input")
    run = commands.add_parser("run")
    run.add_argument("--dataset", default=DEFAULT_DATASET)
    run.add_argument("--mode", choices=["workflow", "plan_execute", "multi_agent"], default="workflow")
    run.add_argument("--orchestrator", choices=["legacy", "controller"],
                     help="Override DEEPTRACE_RESEARCH_ORCHESTRATOR for this experiment")
    run.add_argument("--max-examples", type=int)
    cases = run.add_mutually_exclusive_group()
    cases.add_argument("--case-id", help="Select the original case identity in example metadata.id")
    cases.add_argument("--case-ids", nargs='+', help="Explicit regression cases")
    run.add_argument("--split", help="Evaluate only one LangSmith dataset split, e.g. dev or test")
    run.add_argument("--dataset-version", help="LangSmith dataset version timestamp or tag")
    run.add_argument("--concurrency", type=int, choices=range(1, 7), default=1)
    run.add_argument("--repetitions", type=int, choices=range(1, 11), default=1)
    run.add_argument("--judge", action="store_true", help="Enable an additional reference-based model call per answer")
    run.add_argument("--require-acceptance", action="store_true", help="Fail if any case lacks a passing v4 acceptance score")
    review = commands.add_parser("rescore", help="Native LangSmith re-evaluation using actual writer context")
    review.add_argument("--experiment", required=True)
    review.add_argument("--concurrency", type=int, choices=range(1,7), default=2)
    return cli


async def run_experiment(args, client):
    from deeptrace.application.assembly import build_harness_runtime
    from deeptrace.config import Settings
    from .runner import make_target
    from .evaluators import execution_completed, evidence_sufficient, tool_success_rate
    from .review import trace_grounded_evaluator
    from langchain_openai import ChatOpenAI
    import tempfile
    if args.max_examples is not None and args.max_examples < 1:
        raise ValueError("--max-examples must be positive")
    if args.require_acceptance and not args.judge:
        raise ValueError('--require-acceptance requires --judge')
    examples = list(client.list_examples(dataset_name=args.dataset,
        metadata={"id": args.case_id} if args.case_id else None,
        splits=[args.split] if args.split else None, as_of=args.dataset_version))
    examples.sort(key=lambda example: str((getattr(example, "metadata", None) or {}).get(
        "id", getattr(example, "id", ""))))
    if args.case_ids:
        examples = [example for example in examples if (example.metadata or {}).get('id') in args.case_ids]
        if {example.metadata['id'] for example in examples} != set(args.case_ids):
            raise ValueError('Some requested case ids are missing from the dataset')
    if args.max_examples is not None:
        examples = examples[:args.max_examples]
    if not examples:
        raise ValueError("Dataset has no examples; sync-dataset first")
    settings = Settings.from_env()
    if args.orchestrator is not None:
        settings = replace(settings, research_orchestrator=args.orchestrator)
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                  text=True, timeout=5, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                                   text=True, timeout=5, check=True).stdout)
    except (OSError, subprocess.SubprocessError):
        revision, dirty = "unavailable", None
    grounded = all(bool(example.inputs.get("documents")) for example in examples if hasattr(example, "inputs"))
    metadata = {"mode": args.mode, "reference_scope": "provided_corpus" if grounded else "live_retrieval",
        "research_orchestrator": settings.research_orchestrator,
        "git_revision": revision, "working_tree_dirty": dirty,
        "dataset_version": args.dataset_version, "split": args.split,
        "case_id": args.case_id,
        "case_ids": args.case_ids,
        "judge_enabled": args.judge, "judge_model": settings.openai_model if args.judge else None,
        "judge_rubric": "actual-writer-context-citation-aligned-v4.1" if args.judge else None,
        "model": settings.openai_model, "max_model_calls": settings.max_model_calls,
        "max_input_tokens": settings.max_input_tokens, "max_tool_calls": settings.max_tool_calls,
        "research_max_seconds": settings.research_max_seconds,
        "research_source_target": settings.research_source_target,
        "search_query_count": settings.search_query_count,
        "research_completion_scope": settings.research_completion_scope,
        "model_thinking": settings.model_thinking, "response_fact_review": settings.response_fact_review}
    evaluators = [execution_completed, evidence_sufficient, tool_success_rate]
    if args.judge:
        evaluators.append(trace_grounded_evaluator(client, ChatOpenAI(model=settings.openai_model,
            base_url=settings.openai_base_url, api_key=settings.openai_api_key,
            temperature=0, timeout=60, max_retries=1)))
    # Evaluation writes checkpoint/evidence state only to an isolated temporary DB.
    settings = replace(settings, mysql_dsn="", memory_retrieval="lexical")
    with tempfile.TemporaryDirectory(prefix="deeptrace-eval-") as directory:
        bundle = build_harness_runtime(settings, runs_dir=directory)
        try:
            with tracing_context(client=client, enabled=True):
                results = await aevaluate(make_target(bundle, args.mode), data=examples,
                    evaluators=evaluators, client=client,
                    experiment_prefix=f"deeptrace-{settings.research_orchestrator}-{args.mode}",
                    metadata=metadata,
                    max_concurrency=args.concurrency, num_repetitions=args.repetitions)
            print(f"Experiment: {results.experiment_name}\n{results.url}")
            rows = [row async for row in results]
            failures = sum([bool(row["run"].error) or
                           (row["run"].outputs or {}).get("status") == "failed"
                           for row in rows])
            if failures:
                raise RuntimeError(f"{failures} evaluation target(s) failed; inspect the LangSmith experiment")
            if args.require_acceptance:
                rejected = sum(not any(item.key == 'task_accepted_v4' and item.score == 1
                    for item in row['evaluation_results']['results']) for row in rows)
                if rejected:
                    raise RuntimeError(f'{rejected} task(s) did not meet acceptance; inspect the LangSmith experiment')
        finally:
            await bundle.aclose()


def main():
    load_dotenv()
    args = parser().parse_args()
    client = Client(timeout_ms=60000)
    try:
        if args.command == "sync-dataset":
            records = load_examples(args.file)
            corpus = args.corpus
            if corpus is None and args.file.resolve() == (DATA_DIR / 'research-v1.jsonl').resolve():
                corpus = DATA_DIR / 'frozen-corpus.json'
            if corpus:
                documents = json.loads(corpus.read_text(encoding="utf-8"))
                for record in records:
                    record["inputs"]["documents"] = documents
                    record["metadata"]["scope"] = "provided_corpus"
            dataset = sync_dataset(client, args.dataset, records)
            print(f"Synced {len(records)} examples: {dataset.url}")
        elif args.command == "run":
            asyncio.run(run_experiment(args, client))
        else:
            from deeptrace.config import Settings
            from langchain_openai import ChatOpenAI
            from .review import trace_grounded_evaluator
            settings = Settings.from_env()
            model = ChatOpenAI(model=settings.openai_model, base_url=settings.openai_base_url,
                api_key=settings.openai_api_key, temperature=0, timeout=60, max_retries=1)
            async def rescore():
                project = client.read_project(project_id=args.experiment)
                runs = [run for run in client.list_runs(project_id=project.id, is_root=True)
                        if run.end_time and (run.feedback_stats or {}).get('task_accepted_v4', {}).get('avg') is None]
                if not runs:
                    print('No completed runs awaiting writer-context review')
                    return
                versions = {(run.extra or {}).get('metadata', {}).get('dataset_version') for run in runs}
                if len(versions) != 1:
                    raise ValueError('Review requires one fixed dataset version per experiment')
                examples = {example.id: example for example in client.list_examples(
                    dataset_id=project.reference_dataset_id,
                    example_ids=[run.reference_example_id for run in runs], as_of=versions.pop())}
                aligned = [examples[run.reference_example_id] for run in runs]
                result = await aevaluate(iter(runs), data=aligned, experiment=project,
                    evaluators=[trace_grounded_evaluator(client, model)], client=client,
                    max_concurrency=args.concurrency,
                    metadata={"grounding_evaluator":"actual-writer-context-citation-aligned-v4"})
                print(result.url)
            asyncio.run(rescore())
    finally:
        client.flush()
        client.close()


if __name__ == "__main__":
    main()
