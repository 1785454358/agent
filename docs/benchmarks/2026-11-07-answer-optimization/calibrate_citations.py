"""Validate citation-boundary repair on saved real answers (up to 60 paid calls).

This targeted calibration never rewrites the main v2 scores or gate decision.
Run with the pinned .venv-ragas from backend.
"""

import asyncio
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("evaluation").resolve()))

import claims_quality
import eval_common


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


async def main():
    from openai import AsyncOpenAI

    root = Path("..").resolve()
    old_root = root / "tmp/real-evaluation-20261107"
    new_root = root / "tmp/answer-optimization-20261107"
    output = new_root / "citation-calibration"
    output.mkdir(parents=True, exist_ok=False)
    old_module = new_root / "workflow/source_snapshot/backend/evaluation/claims_quality.py"
    spec = importlib.util.spec_from_file_location("claims_quality_v2", old_module)
    before_parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(before_parser)
    inputs = {"before": old_root / "research-batch/quality_eval.json",
              "after": new_root / "workflow/quality_eval.json"}
    payloads = {label: read(path) for label, path in inputs.items()}
    historical = {label: {r["run_id"]: r for r in read(folder / "claims/claims_scores.json")["results"]}
                  for label, folder in (("before", old_root), ("after", new_root))}
    selected_ids = {"single_hop-dev-02", "version_boundary-dev-01"}
    replay, selected = [], []
    for label, payload in payloads.items():
        eval_common.validate_export(payload)
        for sample in payload["samples"]:
            record = sample["record"]
            if record["mode"] != "workflow":
                continue
            prior, prior_uses, prior_outcome = before_parser._citation_items(record, max_citations=12)
            after, after_uses, after_outcome = claims_quality._citation_items(record, max_citations=12)
            replay.append({"version": label, "question_id": record["question_id"],
                           "before_uses": prior_uses, "after_uses": after_uses,
                           "before_outcome": prior_outcome, "after_outcome": after_outcome,
                           "before_sentences": [p["sentence"] for p in prior or []],
                           "after_sentences": [p["sentence"] for p in after or []]})
            if record["question_id"] in selected_ids:
                selected.append((label, sample))
    config = eval_common.env_config(".env")
    judge = {**read(new_root / "claims/identity.json")["judge"],
             "adapter": claims_quality.ADAPTER_VERSION,
             "scorer_sha256": hashlib.sha256(Path(claims_quality.__file__).read_bytes()).hexdigest()}
    identity = {"purpose": "targeted citation-boundary calibration, not a whole-matrix score update",
                "selected_question_ids": sorted(selected_ids), "modes": ["workflow"],
                "input_sha256": {label: eval_common.digest(value) for label, value in payloads.items()},
                "judge": judge, "max_provider_attempts": 60, "max_citations": 12,
                "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    eval_common.atomic_json(output / "identity.json", identity)
    ledger = eval_common.AttemptLedger(output / "attempts.json", 60)
    results = []
    async with AsyncOpenAI(api_key=config["OPENAI_API_KEY"], base_url=config["OPENAI_BASE_URL"],
                           max_retries=0, timeout=60) as client:
        async def call(**kwargs):
            for key, value in judge["request_options"].items():
                kwargs.setdefault(key, value)
            return await ledger.invoke(client.chat.completions.create, **kwargs)

        for label, sample in selected:
            record = sample["record"]
            result = await claims_quality.score_citation_accuracy(
                sample, call, model=judge["model"], max_tokens=2048, max_citations=12)
            row = {"version": label, "question_id": record["question_id"], "run_id": record["run_id"],
                   "sample_sha256": eval_common.digest(sample),
                   "old_v2_metric": historical[label][record["run_id"]]["metrics"]["citation_accuracy"],
                   "corrected_v3_metric": result}
            results.append(row)
            eval_common.atomic_json(output / "progress.json", {"results": results, "usage": ledger.snapshot()})
            print(json.dumps({"version": label, "question_id": record["question_id"],
                              "v2": row["old_v2_metric"]["value"], "v3": result["value"],
                              "status": result["status"]}), flush=True)
    report = {"identity": identity, "results": results, "usage": ledger.snapshot(),
              "offline_boundary_replay": replay,
              "limitations": ["Four targeted saved answers; not a new 12-task quality estimate",
                              "v2 and v3 metric values have different segmentation and are not Agent improvement deltas",
                              "Historical v2 scores and failed gate are preserved unchanged"]}
    eval_common.atomic_json(output / "calibration.json", report)
    public = Path(__file__).resolve().parent
    eval_common.atomic_json(public / "citation-calibration.json", report)


if __name__ == "__main__":
    asyncio.run(main())
