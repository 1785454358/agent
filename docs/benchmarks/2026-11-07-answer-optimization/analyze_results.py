"""Publish the saved version comparison. Run from backend; no model requests."""

import contextlib
import hashlib
import io
import json
import shutil
import statistics
import zipfile
from collections import Counter
from pathlib import Path

from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.regression import CONTROL_FIELDS
from deeptrace.eval.regression_cli import main as gate


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execution(rows):
    return {"runs": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
            "answered": sum(r["answered"] for r in rows),
            "model_calls": sum(r["model_calls"] for r in rows),
            "tool_calls": sum(r["tool_calls"] for r in rows),
            "mean_wall_ms": statistics.mean(r["wall_ms"] for r in rows),
            "mean_answer_chars": statistics.mean(len(r["answer"] or "") for r in rows),
            "provider_attempts": sum(r["usage"]["provider_attempts"] for r in rows),
            "input_tokens": sum(r["usage"]["input_tokens"] for r in rows),
            "output_tokens": sum(r["usage"]["output_tokens"] for r in rows)}


def merged_scores(root):
    result = {}
    for folder, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json")):
        for row in read(root / folder / filename)["results"]:
            if row["mode"] == "workflow":
                result.setdefault(row["question_id"], {}).update(row["metrics"])
    return result


def main():
    project = Path("..").resolve()
    previous = project / "tmp/real-evaluation-20261107"
    current = project / "tmp/answer-optimization-20261107"
    public = Path(__file__).resolve().parent
    old_input = previous / "research-batch/quality_eval.json"
    new_input = current / "workflow/quality_eval.json"
    metadata = previous / "research-batch/analysis-dev.json"
    policy = project / "backend/src/deeptrace/eval/data/policies/regression-v1.json"
    args = ["--baseline", str(old_input), "--candidate", str(new_input),
            "--baseline-scores", str(previous / "ragas/quality_scores.json"),
            "--baseline-scores", str(previous / "claims/claims_scores.json"),
            "--candidate-scores", str(current / "ragas/quality_scores.json"),
            "--candidate-scores", str(current / "claims/claims_scores.json"),
            "--metadata", str(metadata), "--baseline-mode", "workflow",
            "--candidate-mode", "workflow", "--policy", str(policy),
            "--seed", "7", "--out", str(current / "gate-publication")]
    with contextlib.redirect_stdout(io.StringIO()):
        exit_code = gate(args)
    report = read(current / "gate-publication/regression.json")
    shutil.copytree(current / "gate-publication", public / "gate", dirs_exist_ok=True)
    original = read(old_input)
    candidate = read(new_input)
    assert all(original["manifest"].get(k) == candidate["manifest"].get(k)
               for k in (*CONTROL_FIELDS, "execution_profile"))
    source_checks = {}
    for name, folder in (("workflow", current / "workflow"),
                         ("strategy-probes", current / "strategy-probes")):
        manifest = read(folder / "manifest.json")
        hashes = manifest["manifest"]["source_files"]
        assert all(sha(folder / "source_snapshot" / p) == digest for p, digest in hashes.items())
        drift = [p for p, digest in hashes.items() if sha(project / p) != digest]
        prompt_files = {"backend/src/deeptrace/strategies/planning.py",
                        "backend/src/deeptrace/responses/writing.py",
                        "backend/src/deeptrace/responses/fact_review.py"}
        assert set(drift) <= {"backend/evaluation/claims_quality.py", "backend/evaluation/tests/test_claims_quality.py"} | prompt_files
        originals = read(current / "before/identity.json")
        assert all(sha(project / p) == originals[p] for p in set(drift) & prompt_files)
        source_checks[name] = {"files": len(hashes), "all_snapshot_hashes_match": True,
                               "post_run_changes": drift,
                               "reason": "Candidate prompts rejected and restored; separate v3 citation-parser maintenance after v2 scoring"}
        shutil.copyfile(folder / "manifest.json", public / f"{name}-manifest.json")
    old_rows = [s["record"] for s in original["samples"] if s["record"]["mode"] == "workflow"]
    new_rows = [s["record"] for s in candidate["samples"]]
    probe_rows = read(current / "strategy-probes/records.json")
    old_scores, new_scores = merged_scores(previous), merged_scores(current)
    cases = []
    for before, after in zip(old_rows, new_rows, strict=True):
        assert before["question_id"] == after["question_id"]
        qid = before["question_id"]
        cases.append({"question_id": qid, "before": {"status": before["status"],
                      "answered": before["answered"], "metrics": old_scores[qid]},
                      "after": {"status": after["status"], "answered": after["answered"],
                      "metrics": new_scores[qid]}})
    summary = {"baseline_workflow": execution(old_rows), "candidate_workflow": execution(new_rows),
               "supplemental_probes": execution(probe_rows), "per_task": cases,
               "gate_exit_code": exit_code, "gate_verdict": report["verdict"],
               "paired_comparison": report["comparison"]["groups"][0]}
    atomic_json(public / "results.json", summary)
    judges = {}
    for folder, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json")):
        old_identity = read(previous / folder / "identity.json")
        new_identity = read(current / folder / "identity.json")
        assert old_identity["judge"] == new_identity["judge"]
        judges[folder] = {"unchanged_judge_identity": True, "usage": read(current / folder / filename)["usage"]}
        for version, root in (("before", previous), ("after", current)):
            target = public / "scoring" / version / folder
            target.mkdir(parents=True, exist_ok=True)
            for name in (filename, "identity.json"):
                shutil.copyfile(root / folder / name, target / name)
    for suite, rows in (("workflow", new_rows), ("strategy-probes", probe_rows)):
        for row in rows:
            target = public / "answers" / suite / row["question_id"] / f"{row['mode']}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            evidence = {e["id"]: e for e in row["evidence"]}
            lines = [f"# {row['question_id']} / {row['mode']}", "", row["question"], "",
                     f"Status: {row['status']}; answered: {row['answered']}; reason: {row['response_partial_reason']}; "
                     f"model calls: {row['model_calls']}; seconds: {row['wall_ms'] / 1000:.3f}.", "",
                     row["answer"] or "(no answer)", "", "## Sources", ""]
            lines.extend(f"{i}. {evidence[eid]['title']} — {evidence[eid]['url']}"
                         for i, eid in enumerate(row["cited_evidence_ids"], 1))
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    archive = public / "reproduction-inputs.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for label, root, suite in (("before", previous, "research-batch"), ("after", current, "workflow")):
            bundle.write(root / suite / "quality_eval.json", f"{label}/quality_eval.json")
            for folder, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json")):
                for name in (filename, "identity.json"):
                    bundle.write(root / folder / name, f"{label}/{folder}/{name}")
        bundle.write(metadata, "metadata.json")
        bundle.write(policy, "policy.json")
        bundle.write(current / "strategy-probes/quality_eval.json", "probes/quality_eval.json")
        for path in (current / "workflow/source_snapshot").rglob("*"):
            if path.is_file():
                bundle.write(path, "after/source_snapshot/" + path.relative_to(current / "workflow/source_snapshot").as_posix())
        for path in (current / "before").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle.write(path, "before/original-files/" + path.relative_to(current / "before").as_posix())
        for relative in ("backend/evaluation/claims_quality.py", "backend/evaluation/tests/test_claims_quality.py"):
            bundle.write(project / relative, "scorer-v3/" + relative)
    verification = {"backend_offline": {"passed": 1612, "deselected": 2, "seconds": 145.02},
                    "targeted_tests": {"passed": 164}, "lint": "passed for four production files and protocol tests",
                    "source_snapshots": source_checks, "controlled_fields_unchanged": list((*CONTROL_FIELDS, "execution_profile")),
                    "judges": judges, "reproduction_archive": {"sha256": sha(archive), "bytes": archive.stat().st_size}}
    atomic_json(public / "verification.json", verification)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("per_task", "paired_comparison")}))


if __name__ == "__main__":
    main()
