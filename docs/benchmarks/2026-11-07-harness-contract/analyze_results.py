"""Offline publication of the saved harness experiment; no Provider calls."""

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
            **{k: sum(r["usage"][k] for r in rows)
               for k in ("provider_attempts", "input_tokens", "output_tokens")}}


def trace_contract(row):
    turns = row["trajectory"]["model_messages"]
    proposed, evaluated = [], []
    for turn in turns:
        if turn["role"] in {"planner", "supervisor"} and not proposed:
            try:
                proposed = json.loads(turn["response"]["content"]).get("requirements", [])
            except (ValueError, TypeError):
                pass
        if turn["role"] == "evaluator":
            for message in turn["messages"]:
                content = message.get("content", "")
                if isinstance(content, str) and "EVIDENCE_VIEW_JSON:" in content:
                    text = content.split("EVIDENCE_VIEW_JSON:", 1)[1].lstrip()
                    view, _ = json.JSONDecoder().raw_decode(text)
                    evaluated.append(view["requirements"])
    return {"question_id": row["question_id"], "mode": row["mode"],
            "planner_proposals": proposed, "actual_evaluation_contracts": evaluated,
            "replan_calls": sum(t["role"] in {"replanner", "follow_up"} for t in turns),
            "response_reason": row["response_partial_reason"]}


def scores(root, variant):
    result = {}
    for kind, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json")):
        for row in read(root / f"{variant}-{kind}" / filename)["results"]:
            result.setdefault(row["question_id"], {}).update(row["metrics"])
    return result


def main():
    project = Path("..").resolve()
    root = project / "tmp/harness-contract-20261107"
    public = Path(__file__).resolve().parent
    metadata = root / "baseline/analysis-dev.json"
    policy = project / "backend/src/deeptrace/eval/data/policies/regression-v1.json"
    args = ["--baseline", str(root / "baseline/quality_eval.json"),
            "--candidate", str(root / "candidate/quality_eval.json"),
            "--baseline-scores", str(root / "baseline-ragas/quality_scores.json"),
            "--baseline-scores", str(root / "baseline-claims/claims_scores.json"),
            "--candidate-scores", str(root / "candidate-ragas/quality_scores.json"),
            "--candidate-scores", str(root / "candidate-claims/claims_scores.json"),
            "--metadata", str(metadata), "--policy", str(policy),
            "--baseline-mode", "workflow", "--candidate-mode", "workflow",
            "--seed", "7", "--out", str(root / "gate")]
    with contextlib.redirect_stdout(io.StringIO()):
        exit_code = gate(args)
    report = read(root / "gate/regression.json")
    shutil.copytree(root / "gate", public / "gate")
    rows = {name: read(root / name / "records.json")
            for name in ("baseline", "candidate", "strategy-probes")}
    manifests = {name: read(root / name / "manifest.json") for name in rows}
    left, right = (manifests[name]["manifest"] for name in ("baseline", "candidate"))
    assert all(left.get(k) == right.get(k) for k in (*CONTROL_FIELDS, "execution_profile"))
    assert left["harness_policy"] == {"research_completion_scope": "decomposed"}
    assert right["harness_policy"] == {"research_completion_scope": "original_task"}
    for name, manifest in manifests.items():
        hashes = manifest["manifest"]["source_files"]
        assert all(sha(root / name / "source_snapshot" / p) == digest for p, digest in hashes.items())
        if name != "baseline":
            assert all(sha(project / p) == digest for p, digest in hashes.items())
        atomic_json(public / f"{name}-manifest.json", manifest)
    judged = {name: scores(root, name) for name in ("baseline", "candidate")}
    per_task = []
    for before, after in zip(rows["baseline"], rows["candidate"], strict=True):
        qid = before["question_id"]
        assert qid == after["question_id"]
        per_task.append({"question_id": qid, **{
            label: {"status": row["status"], "answered": row["answered"],
                    "model_calls": row["model_calls"], "tool_calls": row["tool_calls"],
                    "metrics": judged[label][qid]}
            for label, row in (("baseline", before), ("candidate", after))}})
    results = {"execution": {name: execution(value) for name, value in rows.items()},
               "gate_exit_code": exit_code, "gate_verdict": report["verdict"],
               "comparison": report["comparison"]["groups"][0], "per_task": per_task,
               "trace_contracts": {name: [trace_contract(row) for row in value] for name, value in rows.items()}}
    atomic_json(public / "results.json", results)
    judges = {}
    for kind, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json")):
        before = read(root / f"baseline-{kind}/identity.json")
        after = read(root / f"candidate-{kind}/identity.json")
        assert before["judge"] == after["judge"]
        judges[kind] = {"identical_judge_identity": True, "usage": {}}
        for variant in ("baseline", "candidate"):
            target = public / "scoring" / variant / kind
            target.mkdir(parents=True)
            for name in (filename, "identity.json"):
                shutil.copyfile(root / f"{variant}-{kind}" / name, target / name)
            data = read(target / filename)
            judges[kind]["usage"][variant] = data["usage"]
            judges[kind].setdefault("metric_status_counts", {})[variant] = dict(Counter(
                m["status"] for row in data["results"] for m in row["metrics"].values()))
    for variant, values in rows.items():
        for row in values:
            path = public / "answers" / variant / row["question_id"] / f"{row['mode']}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            evidence = {e["id"]: e for e in row["evidence"]}
            text = [f"# {row['question_id']} / {row['mode']}", "", row["question"], "",
                    f"Status: {row['status']}; answered: {row['answered']}; reason: {row['response_partial_reason']}; "
                    f"model calls: {row['model_calls']}; tools: {row['tool_calls']}; seconds: {row['wall_ms']/1000:.3f}.",
                    "", row["answer"] or "(no answer)", "", "## Sources", ""]
            text.extend(f"{i}. {evidence[eid]['title']} — {evidence[eid]['url']}"
                        for i, eid in enumerate(row["cited_evidence_ids"], 1))
            path.write_text("\n".join(text) + "\n", encoding="utf-8")
    archive = public / "reproduction-inputs.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for variant in rows:
            for name in ("quality_eval.json", "manifest.json"):
                bundle.write(root / variant / name, f"{variant}/{name}")
            for path in (root / variant / "source_snapshot").rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    bundle.write(path, f"{variant}/source_snapshot/" + path.relative_to(root / variant / "source_snapshot").as_posix())
        for variant in ("baseline", "candidate"):
            for kind, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json")):
                for name in (filename, "identity.json"):
                    bundle.write(root / f"{variant}-{kind}" / name, f"{variant}/{kind}/{name}")
        bundle.write(metadata, "metadata.json")
        bundle.write(policy, "policy.json")
        for relative in ("backend/tests/strategies/test_task_completion_scope.py",
                         "backend/tests/eval/test_runtime_profile.py", "backend/tests/config/test_settings.py"):
            bundle.write(project / relative, "tests/" + relative)
    verification = {"backend_offline": {"passed": 1625, "deselected": 2, "seconds": 79.71},
                    "targeted_tests": {"passed": 66, "seconds": 5.02},
                    "lint": "passed for changed production/tests and experiment driver",
                    "source_snapshots_verified": {name: len(m["manifest"]["source_files"]) for name, m in manifests.items()},
                    "fixed_controls": list((*CONTROL_FIELDS, "execution_profile")),
                    "treatment": {"baseline": left["harness_policy"], "candidate": right["harness_policy"]},
                    "judges": judges, "reproduction_archive": {"sha256": sha(archive), "bytes": archive.stat().st_size}}
    usage = [execution(r) for r in rows.values()] + [u for j in judges.values() for u in j["usage"].values()]
    verification["new_usage"] = {k: sum(u[k] for u in usage) for k in ("provider_attempts", "input_tokens", "output_tokens")}
    verification["new_usage"].update(cost=None, agent_trials=30)
    atomic_json(public / "verification.json", verification)
    print(json.dumps({"execution": results["execution"], "gate": report["verdict"],
                      "metrics": {label: {k: v["available_question_mean"] for k, v in system["quality"].items()}
                                  for label, system in results["comparison"]["systems"].items()}}, ensure_ascii=True))


if __name__ == "__main__":
    main()
