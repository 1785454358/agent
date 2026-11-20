"""Compare the component replay with its immutable historical parent, offline."""

import argparse
import json
import statistics
from pathlib import Path

from deeptrace.eval.analysis_inputs import load_analysis_inputs
from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.trajectory import _content_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("replay-source-first-numeric", "replay-request-bound", "replay-request-bound-repair"), required=True)
    args = parser.parse_args()
    project = Path("..").resolve()
    baseline = project / "tmp/harness-contract-20261107"
    current = project / "tmp/answer-review-boundary-20261108"
    variant = args.variant
    metadata = baseline / "baseline/analysis-dev.json"

    def load(root, name):
        return load_analysis_inputs(root / name / "quality_eval.json", [
            root / f"{name}-ragas/quality_scores.json",
            root / f"{name}-claims/claims_scores.json"], metadata)

    before, after = load(baseline, "baseline"), load(current, variant)
    assert before.metric_judges == after.metric_judges
    for key in ("model", "dataset_sha256", "corpus_sha256", "response_mode"):
        assert before.payload["manifest"][key] == after.payload["manifest"][key]
    protocol = after.payload["manifest"]["experiment_protocol"]
    assert protocol["parent_input_sha256"] == _content_hash(before.payload)
    assert after.payload["manifest"]["execution_profile"]["parent_identity"] == before.payload["identity_sha256"]
    rows = [{r["question_id"]: r for r in item.records} for item in (before, after)]
    scores = [{r["question_id"]: r["metrics"] for r in item.scores} for item in (before, after)]
    assert set(rows[0]) == set(rows[1]) == set(scores[0]) == set(scores[1])
    metrics, per_task = {}, []
    for name in sorted(before.metric_judges):
        paired, states = [], []
        for qid in rows[0]:
            left, right = (s[qid][name] for s in scores)
            states.append({"question_id": qid, "baseline": left["status"], "candidate": right["status"]})
            if left["status"] == right["status"] == "ok":
                paired.append((left["value"], right["value"]))
        metrics[name] = {"paired_tasks": len(paired), "statuses": states,
            "baseline_mean": statistics.mean(a for a, _ in paired) if paired else None,
            "candidate_mean": statistics.mean(b for _, b in paired) if paired else None,
            "delta": statistics.mean(b - a for a, b in paired) if paired else None}
    for qid in rows[0]:
        per_task.append({"question_id": qid, **{label: {
            "status": rs[qid]["status"], "chars": len(rs[qid]["answer"]),
            "unresolved_gaps": rs[qid]["unresolved_gaps"], "metrics": ss[qid]}
            for label, rs, ss in zip(("baseline", "candidate"), rows, scores, strict=True)}})
    f1 = metrics["factual_correctness"]
    checks = {
        "all_twelve_outputs_and_score_records": len(rows[1]) == 12 and all(r["answer"] for r in rows[1].values()),
        "all_goal_and_f1_scores_available": all(metrics[m]["paired_tasks"] == 12 for m in (
            "agent_goal_accuracy", "factual_correctness")),
        "goal_not_lower": metrics["agent_goal_accuracy"]["delta"] is not None and metrics["agent_goal_accuracy"]["delta"] >= 0,
        "f1_improvement_at_least_005": f1["delta"] is not None and f1["delta"] >= 0.05,
        "no_quality_mean_drop_over_002": all(metrics[m]["delta"] is not None and metrics[m]["delta"] >= -0.02
            for m in ("faithfulness", "claim_groundedness", "citation_accuracy")),
        "no_loss_of_available_quality_scores": all(not (s["baseline"] == "ok" and s["candidate"] != "ok")
            for m in ("faithfulness", "claim_groundedness", "citation_accuracy") for s in metrics[m]["statuses"]),
        "no_task_f1_drop_over_020": all(p["candidate"]["metrics"]["factual_correctness"]["status"] == "ok"
            and p["baseline"]["metrics"]["factual_correctness"]["status"] == "ok"
            and p["candidate"]["metrics"]["factual_correctness"]["value"] - p["baseline"]["metrics"]["factual_correctness"]["value"] >= -0.20
            for p in per_task),
    }
    report = {"kind": "component-only; historical parent review versus new source-first completion",
        "limitations": ["Not an end-to-end Agent run or a full-run regression gate.",
            "One observation per task; reused baseline review was generated earlier.",
            "Faithfulness and groundedness paired means cover available scores only; N/A remains unknown.",
            "Agent semantic audit is required in addition to these automatic continuation checks."],
        "provenance": {"baseline": before.provenance, "candidate": after.provenance},
        "metrics": metrics, "checks": checks, "automatic_continuation_checks_pass": all(checks.values()),
        "per_task": per_task}
    atomic_json(current / f"component-{variant}.json", report)
    print(json.dumps({"metrics": {k: {n: v[n] for n in ("paired_tasks", "baseline_mean", "candidate_mean", "delta")}
        for k, v in metrics.items()}, "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
