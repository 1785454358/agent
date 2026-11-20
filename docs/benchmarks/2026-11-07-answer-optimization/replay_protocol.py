"""Offline structural replay of immutable model responses; no model requests."""

import importlib.util
import json
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from deeptrace.eval.artifacts import atomic_json
from deeptrace.strategies.evidence_references import parse_reference_evaluation
from deeptrace.strategies.multi_agent.models import ReferenceSupervisorEvaluation
from deeptrace.strategies.plan_execute.models import ReferenceExecutorDecision
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation


def errors(parser, schema, text):
    try:
        parser(schema, text)
    except ValidationError as exc:
        return [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
    return []


def main():
    root = Path("..").resolve()
    old_file = root / "tmp/answer-optimization-20261107/before/backend/src/deeptrace/strategies/evidence_references.py"
    spec = importlib.util.spec_from_file_location("original_reference_protocol", old_file)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    source = root / "tmp/real-evaluation-20261107/research-batch/records.json"
    records = json.loads(source.read_text(encoding="utf-8"))
    schemas = {"workflow": ReferenceWorkflowEvaluation,
               "plan_execute": ReferenceExecutorDecision,
               "multi_agent": ReferenceSupervisorEvaluation}
    rows = []
    for record in records:
        schema = schemas.get(record["mode"])
        if schema is None:
            continue
        for turn in record["trajectory"]["model_messages"]:
            # Only actual evidence judgments have the reference schema.
            text = turn["response"].get("content", "")
            if not any("EVIDENCE_VIEW_JSON" in str(m.get("content", ""))
                       for m in turn["messages"]):
                continue
            rows.append({"question_id": record["question_id"], "mode": record["mode"],
                         "sequence": turn["sequence"], "role": turn["role"],
                         "before_errors": errors(old.parse_reference_evaluation, schema, text),
                         "after_errors": errors(parse_reference_evaluation, schema, text)})
    report = {"reviewer": "Agent structural replay; no semantic regrading",
              "source": str(source), "total": len(rows),
              "before_valid": sum(not r["before_errors"] for r in rows),
              "after_valid": sum(not r["after_errors"] for r in rows),
              "by_mode": dict(Counter(r["mode"] for r in rows)), "responses": rows}
    output = Path(__file__).resolve().parent / "protocol-replay.json"
    atomic_json(output, report)
    print(json.dumps({k: v for k, v in report.items() if k != "responses"}))


if __name__ == "__main__":
    main()
