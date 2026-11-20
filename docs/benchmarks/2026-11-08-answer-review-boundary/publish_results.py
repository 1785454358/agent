"""Publish immutable component experiments and the narrow production fix."""

import contextlib
import difflib
import hashlib
import io
import json
import re
import shutil
import statistics
import zipfile
from collections import Counter
from pathlib import Path

from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.regression_cli import main as gate


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execution(rows):
    return {"runs": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
        "mean_answer_chars": statistics.mean(len(r["answer"]) for r in rows),
        **{k: sum(r["usage"][k] for r in rows)
           for k in ("provider_attempts", "input_tokens", "output_tokens")}}


def main():
    project = Path("..").resolve()
    root = project / "tmp/answer-review-boundary-20261108"
    baseline = project / "tmp/harness-contract-20261107"
    public = Path(__file__).resolve().parent
    (public / "manifests").mkdir(exist_ok=True)
    variants = ("replay", "replay-source-first", "replay-source-first-numeric",
                "replay-request-bound", "replay-request-bound-repair")
    manifests, executions = {}, {}
    for variant in variants:
        manifest = read(root / variant / "manifest.json")
        files = manifest["manifest"]["source_files"]
        assert all(sha(root / variant / "source_snapshot" / p) == digest for p, digest in files.items())
        manifests[variant] = {"identity_sha256": manifest["identity_sha256"], "verified_source_files": len(files)}
        rows = read(root / variant / "records.json")
        assert len(rows) == 12
        executions[variant] = execution(rows)
        atomic_json(public / "manifests" / f"{variant}.json", manifest)
        for row in rows:
            target = public / "answers" / variant / f"{row['question_id']}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            text = [f"# {row['question_id']}", "", row["question"], "",
                    f"Component status: {row['status']}; error: {row['system_error']}; "
                    f"new Provider calls: {row['usage']['provider_attempts']}.", "",
                    row["answer"] or "(Rejected output; see raw response in the archive.)", "",
                    "Unresolved gaps: " + json.dumps(row["unresolved_gaps"], ensure_ascii=False), ""]
            target.write_text("\n".join(text), encoding="utf-8")
    comparisons = {}
    usage = [executions[v] for v in variants]
    for variant in ("replay-source-first-numeric", "replay-request-bound-repair"):
        name = f"component-{variant}.json"
        shutil.copyfile(root / name, public / name)
        comparisons[variant] = read(root / name)
        for kind, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json")):
            source = root / f"{variant}-{kind}"
            target = public / "scoring" / variant / kind
            target.mkdir(parents=True, exist_ok=True)
            for file in ("identity.json", filename):
                shutil.copyfile(source / file, target / file)
            usage.append(read(source / filename)["usage"])
    for kind, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json")):
        target = public / "scoring/baseline" / kind
        target.mkdir(parents=True, exist_ok=True)
        for file in ("identity.json", filename):
            shutil.copyfile(baseline / f"baseline-{kind}" / file, target / file)

    valid = read(root / "recovery-verification/historical-valid-replays.json")
    repaired = read(root / "recovery-verification/live-repair.json")
    assert len(valid) == 12 and all(r["review_unchanged"] and r["first_request_byte_identical"] for r in valid)
    assert repaired["usage"]["provider_attempts"] == 1 and repaired["same_human_payload"]
    assert all(sha(project / p) == digest for p, digest in repaired["source_files"].items())
    shutil.copytree(root / "recovery-verification", public / "recovery-verification", dirs_exist_ok=True)
    usage.append(repaired["usage"])
    before = root / "before/backend/src/deeptrace/responses"
    assert (before / "graph.py").read_bytes() == (project / "backend/src/deeptrace/responses/graph.py").read_bytes()
    current = project / "backend/src/deeptrace/responses/fact_review.py"
    diff = "".join(difflib.unified_diff(
        (before / "fact_review.py").read_text(encoding="utf-8").splitlines(keepends=True),
        current.read_text(encoding="utf-8").splitlines(keepends=True),
        fromfile="before/backend/src/deeptrace/responses/fact_review.py",
        tofile="after/backend/src/deeptrace/responses/fact_review.py"))
    (public / "production-changes.patch").write_text(diff, encoding="utf-8")

    # Locate the actual missing source paragraph, without adding it to generation.
    payload = read(baseline / "baseline/quality_eval.json")
    record = next(s["record"] for s in payload["samples"] if s["record"]["question_id"] == "multi_hop-dev-02")
    evidence = next(e for e in record["evidence"] if e["title"] == "Interrupts")
    material = next(m for m in read(root / "replay/materials.json") if m["question_id"] == record["question_id"])
    found = re.search(r"same.{0,40}thread", evidence["body"], re.IGNORECASE)
    start = evidence["body"].rfind("\n\n", 0, found.start()) + 2
    end = evidence["body"].find("\n\n", found.end())
    witness = evidence["body"][start:end]
    assert witness and not any(witness in s for s in material["sources"])
    incident = {"question_id": record["question_id"], "original_question": record["question"],
        "source_url": evidence["url"], "source_body_sha256": hashlib.sha256(evidence["body"].encode()).hexdigest(),
        "missing_original_paragraph": {"start": start, "end": end, "text": witness},
        "present_in_final_visible_sources": False,
        "observed_effect": "The final visible Interrupts passage has Command resumption but no same-thread condition.",
        "scope_of_conclusion": "A confirmed source-handoff omission on this saved case; not a general recall rate.",
        "status": "diagnosed; semantic candidate rejected; retrieval/source selection remains unresolved"}
    atomic_json(public / "source-handoff-incident.json", incident)

    # A component export must not be accepted as a controlled full Agent trial.
    args = ["--baseline", str(baseline / "baseline/quality_eval.json"),
        "--candidate", str(root / "replay-request-bound-repair/quality_eval.json"),
        "--baseline-scores", str(baseline / "baseline-ragas/quality_scores.json"),
        "--baseline-scores", str(baseline / "baseline-claims/claims_scores.json"),
        "--candidate-scores", str(root / "replay-request-bound-repair-ragas/quality_scores.json"),
        "--candidate-scores", str(root / "replay-request-bound-repair-claims/claims_scores.json"),
        "--metadata", str(baseline / "baseline/analysis-dev.json"),
        "--policy", str(project / "backend/src/deeptrace/eval/data/policies/regression-v1.json"),
        "--baseline-mode", "workflow", "--candidate-mode", "workflow", "--seed", "7",
        "--out", str(root / "component-full-gate-check")]
    stream = io.StringIO()
    gate_output = root / "component-full-gate-check"
    if gate_output.exists() and any(gate_output.iterdir()):
        gate_output = root / "component-full-gate-reproduction"
    args[-1] = str(gate_output)
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        try:
            code = gate(args)
        except SystemExit as exc:
            code = exc.code
    assert code == 2 and "experiment control mismatch: limits" in stream.getvalue()
    rejection = {"exit_code": code, "output": stream.getvalue(), "accepted_as_full_agent_gate_pass": False}
    atomic_json(public / "component-gate-rejection.json", rejection)

    total = {k: sum(u[k] for u in usage) for k in ("provider_attempts", "input_tokens", "output_tokens")}
    total.update(cost=None, controlled_component_generations=60, live_corrective_calls=1,
        newly_generated_full_agent_cohorts=0,
        excluded_usage="An earlier mixed pytest run also executed two real smoke tests; their complete Provider usage was not captured and is excluded from this controlled subtotal.")
    results = {"kind": "component experiments plus a narrow protocol fix; no semantic promotion",
        "executions": executions, "verified_source_snapshots": manifests,
        "candidate_continuation_checks": {k: v["checks"] for k, v in comparisons.items()},
        "semantic_candidate_promoted": False, "full_agent_candidate_run": False,
        "production_change": "one budgeted citation-protocol repair; original first prompts and valid results preserved",
        "recovery_verified": {"historical_valid_replays": 12, "new_live_corrective_calls": 1},
        "controlled_new_usage": total}
    atomic_json(public / "results.json", results)
    archive = public / "reproduction-inputs.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for variant in variants:
            for name in ("quality_eval.json", "manifest.json", "materials.json", "reviews.json"):
                bundle.write(root / variant / name, f"{variant}/{name}")
            for path in (root / variant / "source_snapshot").rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    bundle.write(path, f"{variant}/source_snapshot/" + path.relative_to(root / variant / "source_snapshot").as_posix())
        for name in ("quality_eval.json", "manifest.json", "analysis-dev.json"):
            bundle.write(baseline / "baseline" / name, f"baseline/{name}")
        for path in (baseline / "baseline/source_snapshot").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle.write(path, "baseline/source_snapshot/" + path.relative_to(baseline / "baseline/source_snapshot").as_posix())
        for path in (public / "scoring").rglob("*.json"):
            bundle.write(path, path.relative_to(public).as_posix())
        for path in (public / "recovery-verification").rglob("*.json"):
            bundle.write(path, path.relative_to(public).as_posix())
        for path in public.glob("*.py"):
            bundle.write(path, "drivers/" + path.name)
        for path in (root / "before").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle.write(path, "before/" + path.relative_to(root / "before").as_posix())
        for variant in ("replay-source-first-numeric", "replay-request-bound-repair"):
            for kind in ("ragas", "claims"):
                for path in (root / f"{variant}-{kind}").glob("*.json"):
                    if path.name not in {"identity.json", "quality_scores.json", "claims_scores.json"}:
                        bundle.write(path, f"scoring/{variant}/{kind}/" + path.name)
        bundle.write(project / "backend/src/deeptrace/eval/data/policies/regression-v1.json", "policy.json")
        bundle.write(public / "README.md", "README.md")
        for name in ("component-replay-source-first-numeric.json", "component-replay-request-bound-repair.json",
                     "results.json", "source-handoff-incident.json", "component-gate-rejection.json", "production-changes.patch"):
            bundle.write(public / name, name)
        for rel in ("backend/src/deeptrace/responses/fact_review.py", "backend/src/deeptrace/responses/graph.py",
                    "backend/tests/responses/test_review_recovery.py"):
            bundle.write(project / rel, "production/" + rel)
    atomic_json(public / "verification.json", {
        "final_production_source_sha256": sha(current), "graph_restored_byte_for_byte": True,
        "first_review_requests_unchanged": 12, "historical_valid_reviews_unchanged": 12,
        "live_repair_new_provider_attempts": 1, "full_agent_gate_rejects_component_profile": code == 2,
        "reproduction_archive": {"sha256": sha(archive), "bytes": archive.stat().st_size},
        "limitations": ["No new full 12-task Agent candidate was run after the component failed.",
            "Historical trace replay is not a fresh model request.",
            "Independent scores do not demonstrate an overall factual-F1 improvement.",
            "Selected-source full bodies are the existing faithfulness context, not exact writer-visible excerpts.",
            "Final production regression/lint and credential scan are recorded separately after completion."]})
    print(json.dumps({"usage": total, "archive_bytes": archive.stat().st_size,
                      "source_snapshots": manifests, "component_gate_exit": code}, ensure_ascii=False))


if __name__ == "__main__":
    main()
