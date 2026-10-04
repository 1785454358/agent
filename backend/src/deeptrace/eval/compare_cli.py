"""Offline: python -m deeptrace.eval.compare_cli --help."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.comparison import compare_records, render_comparison
from deeptrace.eval.trajectory import _content_hash


def _read(path):
    target = Path(path)
    if target.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("analysis input exceeds 64 MiB")
    return json.loads(target.read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="quality_eval.json v2")
    parser.add_argument(
        "--scores", required=True, help="associated quality_scores.json"
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help="asset hashes and explicit per-question dataset/split/kind/category",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args(argv)
    try:
        payload, scores, metadata = (
            _read(args.input),
            _read(args.scores),
            _read(args.metadata),
        )
        if not all(isinstance(item, dict) for item in (payload, scores, metadata)):
            raise ValueError("JSON objects required")
        if (
            payload.get("schema_version") != 2
            or _content_hash(payload["manifest"]) != payload["identity_sha256"]
        ):
            raise ValueError("experiment manifest integrity mismatch")
        if scores.get("experiment_identity") != payload["identity_sha256"]:
            raise ValueError("judge experiment identity mismatch")
        judge_identity = _read(Path(args.scores).parent / "identity.json")
        if (
            not isinstance(judge_identity, dict)
            or judge_identity.get("input_sha256") != _content_hash(payload)
            or judge_identity.get("judge") != scores.get("judge")
        ):
            raise ValueError("exact judged input or judge identity mismatch")
        for name in ("dataset_sha256", "corpus_sha256"):
            if metadata.get(name) != payload["manifest"][name]:
                raise ValueError("analysis metadata asset identity mismatch")
        report = compare_records(
            [s["record"] for s in payload["samples"]],
            scores["results"],
            metadata=metadata["questions"],
            seed=args.seed,
            resamples=args.resamples,
        )
        report["provenance"] = {
            "experiment_identity": payload["identity_sha256"],
            "quality_scores_sha256": hashlib.sha256(
                Path(args.scores).read_bytes()
            ).hexdigest(),
            "metadata_sha256": _content_hash(metadata),
            "judged_input_sha256": judge_identity["input_sha256"],
            "judge": scores.get("judge"),
            "human_review": scores.get("human_review"),
        }
        output = Path(args.out)
        if output.is_symlink() or any(
            p.is_symlink() for p in output.absolute().parents
        ):
            raise ValueError("analysis output symlink refused")
        if output.exists() and any(output.iterdir()):
            raise ValueError("nonempty analysis directory refused")
        output.mkdir(parents=True, exist_ok=True)
        atomic_json(output / "comparison.json", report)
        (output / "comparison.md").write_text(
            render_comparison(report), encoding="utf-8"
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(
            type(exc).__name__ + ": invalid analysis identity, input or output"
        )
    print(render_comparison(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
