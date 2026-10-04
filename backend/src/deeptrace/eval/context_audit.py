"""Development-only literal-span delivery diagnosis, not answer-quality scoring."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from collections import Counter
from pathlib import Path

from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.eval.artifacts import ExperimentStore, atomic_json
from deeptrace.eval.assets import (
    BenchmarkAssets,
    default_benchmark_path,
    load_benchmark,
)
from deeptrace.eval.experiment import EvaluationLimits, ModelIdentity, build_manifest
from deeptrace.eval.runner import RunRecord, run_matrix
from deeptrace.eval.scripted import ScriptedResearchModel

DEFAULT_TASKS = (
    "single_hop-dev-01",
    "multi_hop-dev-02",
    "version_boundary-dev-02",
)
STAGES = (
    "not_fetched",
    "stored_not_selected",
    "selected_not_visible",
    "visible",
    "unknown_no_responder",
)


def analyze_delivery(assets: BenchmarkAssets, records: list[RunRecord]) -> dict:
    """Only analyze after execution; never provide reference positions to runtime."""
    if assets.split != "dev" or not records:
        raise ValueError("nonempty development-only records required")
    questions = {q.id: q for q in assets.bundle.tasks if q.split == assets.split}
    documents = {d.url: d for d in assets.corpus.documents()}
    sources = {s.id: s for s in assets.bundle.sources}
    seen = set()
    rows = []
    for record in records:
        question = questions.get(record.question_id)
        if (
            not question
            or record.question != question.question
            or record.run_id in seen
        ):
            raise ValueError("unknown/mismatched question or duplicate run")
        seen.add(record.run_id)
        turns = record.trajectory.get("model_messages")
        if not isinstance(turns, list) or record.artifact_errors:
            raise ValueError("complete evidence and model-message traces required")
        responder = []
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("messages"), list):
                raise ValueError("invalid model-message trace")
            if turn.get("role") == "responder":
                contents = []
                for message in turn["messages"]:
                    if not isinstance(message, dict) or not isinstance(
                        message.get("content"), str
                    ):
                        raise ValueError("text responder trace required")
                    contents.append(message["content"])
                responder.append("\n".join(contents))
        for evidence in record.evidence:
            document = documents.get(evidence.get("url"))
            if document is None or evidence.get("body") != document.body:
                raise ValueError("evidence does not match frozen corpus")
            actual_hash = hashlib.sha256(document.body.encode("utf-8")).hexdigest()
            if evidence.get("content_sha256") != actual_hash:
                raise ValueError("evidence hash mismatch")
        for ref in question.references:
            source = sources[ref.source_id]
            fetched = [e for e in record.evidence if e["url"] == source.url]
            selected = [e for e in fetched if e.get("selected_for_outcome")]
            visible = [i for i, text in enumerate(responder) if ref.quote in text]
            if not fetched:
                stage = "not_fetched"
            elif not selected:
                stage = "stored_not_selected"
            elif not responder:
                stage = "unknown_no_responder"
            elif not visible:
                stage = "selected_not_visible"
            else:
                stage = "visible"
            rows.append(
                {
                    "run_id": record.run_id,
                    "question_id": record.question_id,
                    "system": record.mode,
                    "application_status": record.status,
                    "source_id": source.id,
                    "source_url": source.url,
                    "source_chars": len(documents[source.url].body),
                    "start_line": ref.start_line,
                    "end_line": ref.end_line,
                    "span_kind": ref.kind,
                    "stored": bool(fetched),
                    "selected": bool(selected),
                    "responder_turns_with_span": visible,
                    "responder_turn_count": len(responder),
                    "delivery_stage": stage,
                }
            )
    counts = Counter(row["delivery_stage"] for row in rows)
    return {
        "schema_version": 1,
        "kind": "literal_span_delivery_diagnostic",
        "benchmark_identity": assets.identity,
        "split": assets.split,
        "runs": len(records),
        "counts": {stage: counts[stage] for stage in STAGES},
        "rows": rows,
        "limitations": [
            "Exact full-span presence in responder input, "
            "not semantic support or answer correctness.",
            "A partial span, paraphrase or research finding may convey facts "
            "even if the full span is absent.",
            "Scope-boundary references do not establish a semantic abstention score.",
            "Only selected sources and responder messages are inspected; "
            "absence alone is not proof of the truncation cause.",
            "Scripted development diagnostic, "
            "not a real-model benchmark or held-out test result.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=default_benchmark_path())
    parser.add_argument("--question-id", action="append")
    parser.add_argument(
        "--response-mode", choices=[m.value for m in ResponseMode], default="answer"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        assets = load_benchmark(args.bundle, split="dev")
        ids = args.question_id or list(DEFAULT_TASKS)
        questions = {q.id: q for q in assets.questions}
        if len(ids) != len(set(ids)) or any(i not in questions for i in ids):
            raise ValueError("unique development task IDs required")
        selected = [questions[i] for i in ids]
        output = args.out
        if (
            output.is_symlink()
            or any(p.is_symlink() for p in output.absolute().parents)
            or (output.exists() and any(output.iterdir()))
        ):
            raise ValueError("empty nonsymlink diagnostic directory required")
        limits = EvaluationLimits(max_batch_model_calls=240)
        manifest = build_manifest(
            selected,
            assets.corpus,
            model=ModelIdentity(kind="scripted", name="scripted-research-v1"),
            modes=["workflow", "baseline"],
            repeats=1,
            run_prefix="context-audit",
            limits=limits,
            response_mode=args.response_mode,
            response_max_content_chars=600,
        )
        manifest["diagnostic"] = {
            "kind": "literal_span_delivery",
            "benchmark_identity": assets.identity,
            "question_ids": ids,
            "split": "dev",
        }
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        with ExperimentStore(output, manifest) as store:
            records = asyncio.run(
                run_matrix(
                    selected,
                    assets.corpus,
                    model_factory=ScriptedResearchModel,
                    modes=(ResearchMode.WORKFLOW,),
                    run_prefix="context-audit",
                    limits=limits,
                    include_baseline=True,
                    store=store,
                    response_mode=ResponseMode(args.response_mode),
                    response_max_content_chars=600,
                )
            )
            atomic_json(
                output / "records.json", [r.model_dump(mode="json") for r in records]
            )
            atomic_json(output / "delivery.json", analyze_delivery(assets, records))
        return 0
    except (ValueError, OSError) as exc:
        parser.error(f"invalid context audit: {type(exc).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
