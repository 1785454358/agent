"""Offline analysis of the saved real experiment; never sends model requests."""

import contextlib
import hashlib
import io
import json
import shutil
from pathlib import Path

from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.compare_cli import main as compare
from deeptrace.eval.regression_cli import main as gate


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    root = Path("../tmp/real-evaluation-20261107").resolve()
    public = Path(__file__).resolve().parent
    source = root / "research-batch/quality_eval.json"
    metadata = root / "research-batch/analysis-dev.json"
    ragas = root / "ragas/quality_scores.json"
    claims = root / "claims/claims_scores.json"
    args = ["--input", str(source), "--scores", str(ragas), "--scores", str(claims),
            "--metadata", str(metadata), "--seed", "7", "--out", str(root / "comparison")]
    with contextlib.redirect_stdout(io.StringIO()):
        assert compare(args) == 0
    policy = Path("src/deeptrace/eval/data/policies/regression-v1.json").resolve()
    decisions = {}
    for mode in ("workflow", "plan_execute", "multi_agent"):
        args = ["--baseline", str(source), "--candidate", str(source),
                "--baseline-scores", str(ragas), "--baseline-scores", str(claims),
                "--candidate-scores", str(ragas), "--candidate-scores", str(claims),
                "--metadata", str(metadata), "--baseline-mode", "baseline",
                "--candidate-mode", mode, "--policy", str(policy), "--seed", "7",
                "--out", str(root / "gates" / mode)]
        with contextlib.redirect_stdout(io.StringIO()):
            code = gate(args)
        decisions[mode] = {"exit_code": code, "report": read(root / "gates" / mode / "regression.json")}
    report = read(root / "comparison/comparison.json")
    group = report["groups"][0]
    metrics = ("agent_goal_accuracy", "factual_correctness", "faithfulness",
               "claim_groundedness", "citation_accuracy")
    lines = ["# Real-model quality results", "",
             "Same-model automated judges, development tasks only, one trial per task/strategy. "
             "Values are available-case question means; parentheses show scored runs / all runs. "
             "FactualCorrectness is reference-based claim F1, not independently verified factual accuracy.", "",
             "| strategy | goal | factual F1 | faithfulness | claim support | citation accuracy |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for mode, stats in group["systems"].items():
        values = []
        for metric in metrics:
            q = stats["quality"][metric]
            value = q["available_question_mean"]
            value = "N/A" if value is None else f"{value:.3f}"
            values.append(f"{value} ({q['scored_runs']}/{stats['attempted_runs']})")
        lines.append("| " + mode + " | " + " | ".join(values) + " |")
    lines.extend(["", "## Paired differences against Baseline", "",
                  "| strategy | metric | paired tasks | candidate minus baseline | CI95 | excluded tasks |",
                  "| --- | --- | ---: | ---: | --- | ---: |"])
    for mode, comparisons in group["comparisons"].items():
        for metric in metrics:
            s = comparisons[metric]["all_output"]
            lines.append(f"| {mode} | {metric} | {s['paired_tasks']} | {s['difference']} | "
                         f"{s['interval_95']} | {len(s['excluded_tasks'])} |")
    lines.extend(["", "## Example-policy gates", "",
                  "The unchanged example-uncalibrated policy is diagnostic, not a calibrated release standard. "
                  "Point-tolerance failures and insufficient evidence remain separate checks.", ""])
    for mode, result in decisions.items():
        d = result["report"]
        failed = [c["name"] for c in d["checks"] if c["status"] == "fail"]
        unknown = [c["name"] for c in d["checks"] if c["status"] == "inconclusive"]
        lines.append(f"- {mode}: **{d['verdict']}**, exit {result['exit_code']}; "
                     f"failed={failed}; insufficient={unknown}.")
    lines.extend(["", "## Live supplement", "",
                  "These two tasks are separate from the frozen matrix. The retained live Ragas "
                  "run used the earlier 2048-token cap and includes parsing errors. "
                  "Citation scores may cover up to 12 citation uses per answer.", "",
                  "| task | goal | factual F1 | faithfulness | claim support | citation accuracy |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |"])
    live = {}
    for folder, filename in (("live-ragas-v2", "quality_scores.json"),
                             ("live-claims-v2", "claims_scores.json")):
        for row in read(root / folder / filename)["results"]:
            live.setdefault(row["question_id"], {}).update(row["metrics"])
    for qid, scores in live.items():
        values = []
        for metric in metrics:
            v = scores[metric]
            values.append(f"{v['value']:.3f}" if v["status"] == "ok" else f"N/A ({v['status']})")
        lines.append("| " + qid + " | " + " | ".join(values) + " |")
    (public / "quality-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for directory in ("comparison", "gates"):
        shutil.copytree(root / directory, public / directory)
    for directory, filename in (("ragas", "quality_scores.json"), ("claims", "claims_scores.json"),
                                ("live-ragas-v2", "quality_scores.json"),
                                ("live-claims-v2", "claims_scores.json")):
        target = public / "scoring" / directory
        target.mkdir(parents=True)
        for name in (filename, "identity.json"):
            shutil.copyfile(root / directory / name, target / name)
    atomic_json(public / "gate-decisions.json", {
        m: {"exit_code": d["exit_code"], "verdict": d["report"]["verdict"]}
        for m, d in decisions.items()
    })
    audit = {"kind": "real-model artifacts; interrupted pilots kept separately",
             "files": {}}
    for path in root.rglob("*"):
        if (path.is_file() and "source_snapshot" not in path.parts
                and path.suffix != ".log" and path.name != ".writer.lock"):
            audit["files"][path.relative_to(root).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    atomic_json(public / "artifact-index.json", audit)
    print(json.dumps({"mode_scores": {
        m: {k: s["quality"][k]["available_question_mean"] for k in metrics}
        for m, s in group["systems"].items()
    }, "gate_exit_codes": {m: d["exit_code"] for m, d in decisions.items()}}, ensure_ascii=True))


if __name__ == "__main__":
    main()
