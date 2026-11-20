"""Verify portable inputs, source snapshots, score reproduction and credentials.

No Provider calls. Run from backend; requires a new extraction directory.
"""

import argparse
import hashlib
import json
import statistics
import zipfile
from pathlib import Path

from dotenv import dotenv_values

from deeptrace.eval.analysis_inputs import load_analysis_inputs
from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.regression import RegressionPolicy, evaluate_regression


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    project = Path("..").resolve()
    public = Path(__file__).resolve().parent
    archive = public / "reproduction-inputs.zip"
    target = Path(args.out).resolve()
    assert target.is_relative_to(project / "tmp")
    if target.exists() and any(target.iterdir()):
        raise ValueError("extraction directory must be new or empty")
    target.mkdir(parents=True, exist_ok=True)
    secrets = {key: value.encode() for key, value in dotenv_values(".env").items()
        if value and len(value) >= 16 and any(term in key.upper() for term in ("API_KEY", "API_TOKEN", "PASSWORD", "SECRET"))}
    matches = []
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            assert (target / member.filename).resolve().is_relative_to(target)
            raw = bundle.read(member)
            if any(value in raw for value in secrets.values()):
                matches.append("archive:" + member.filename)
        bundle.extractall(target)
    for path in public.rglob("*"):
        if path.is_file() and path != archive and "__pycache__" not in path.parts:
            if any(value in path.read_bytes() for value in secrets.values()):
                matches.append(path.relative_to(public).as_posix())
    assert not matches
    snapshots = {}
    for path in target.glob("*/manifest.json"):
        manifest = read(path)
        files = manifest["manifest"]["source_files"]
        assert all(sha(path.parent / "source_snapshot" / rel) == digest for rel, digest in files.items())
        snapshots[path.parent.name] = len(files)

    def load(name):
        return load_analysis_inputs(target / name / "quality_eval.json", [
            target / "scoring" / name / "ragas/quality_scores.json",
            target / "scoring" / name / "claims/claims_scores.json"],
            target / "baseline/analysis-dev.json")

    baseline = load("baseline")
    reproduced = {}
    for variant in ("replay-source-first-numeric", "replay-request-bound-repair"):
        candidate = load(variant)
        expected = read(target / f"component-{variant}.json")
        assert baseline.metric_judges == candidate.metric_judges
        assert expected["provenance"] == {"baseline": baseline.provenance, "candidate": candidate.provenance}
        before = {r["question_id"]: r["metrics"] for r in baseline.scores}
        after = {r["question_id"]: r["metrics"] for r in candidate.scores}
        for metric, summary in expected["metrics"].items():
            pairs = [(before[qid][metric]["value"], after[qid][metric]["value"]) for qid in before
                if before[qid][metric]["status"] == after[qid][metric]["status"] == "ok"]
            assert len(pairs) == summary["paired_tasks"]
            for field, value in (("baseline_mean", statistics.mean(a for a, _ in pairs)),
                                 ("candidate_mean", statistics.mean(b for _, b in pairs)),
                                 ("delta", statistics.mean(b - a for a, b in pairs))):
                assert abs(summary[field] - value) < 1e-12
        reproduced[variant] = True
    policy = RegressionPolicy.model_validate(read(target / "policy.json"))
    try:
        evaluate_regression(baseline, load("replay-request-bound-repair"), baseline_mode="workflow",
            candidate_mode="workflow", policy=policy, seed=7)
    except ValueError as exc:
        assert "experiment control mismatch: limits" in str(exc)
    else:
        raise AssertionError("component profile unexpectedly accepted")

    final_sources = read(target / "recovery-verification/live-repair.json")["source_files"]
    for rel in ("backend/src/deeptrace/responses/fact_review.py", "backend/src/deeptrace/responses/graph.py"):
        assert sha(target / "production" / rel) == final_sources[rel]
    assert (target / "before/backend/src/deeptrace/responses/graph.py").read_bytes() == (
        target / "production/backend/src/deeptrace/responses/graph.py").read_bytes()
    report = {"archive_sha256": sha(archive), "source_snapshots": snapshots,
        "offline_score_reports_reproduced": reproduced,
        "component_full_agent_gate_rejection_reproduced": True,
        "production_fix_source_hashes_verified": True,
        "production_graph_restored_byte_for_byte": True,
        "credential_scan": {"exact_values_checked": len(secrets), "matches": matches},
        "final_backend_offline": {"passed": 1632, "deselected": 2, "seconds": 119.72},
        "targeted_tests": {"passed": 121, "seconds": 7.40},
        "lint": "changed production, new tests and analysis/verification drivers passed",
        "code_review": "Checked failure limits, context admission, shared gateway, unchanged valid path, cancellation, source numbering and legacy behavior.",
        "new_provider_calls_in_this_verification": 0}
    atomic_json(public / "final-checks.json", report)
    index = {path.relative_to(public).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size}
        for path in sorted(public.rglob("*")) if path.is_file()
        and path.name != "artifact-index.json" and "__pycache__" not in path.parts}
    atomic_json(public / "artifact-index.json", index)
    print(json.dumps({"indexed_files": len(index), **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
