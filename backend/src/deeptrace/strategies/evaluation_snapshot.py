"""Run-local, checkpointable evaluation dependencies; uncertainty invalidates reuse."""

import hashlib
import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel

RULE_VERSION = "evidence-evaluation-20261118-v1"


@lru_cache(maxsize=1)
def rule_digest():
    root = Path(__file__).resolve().parents[1]
    paths = ("strategies/evaluation_snapshot.py", "strategies/evaluation_delta.py", "strategies/evidence_evaluation.py",
             "strategies/evaluation_materials.py", "strategies/evaluation_schema.py",
             "strategies/evidence_references.py", "strategies/publication_dates.py",
             "tools/evidence_units.py", "tools/evidence_views.py", "tools/source_sections.py", "harness/prompts.py",
             "research/verification.py", "research/evidence_graph.py")
    digest = hashlib.sha256(RULE_VERSION.encode())
    for path in paths:
        digest.update((root / path).read_bytes())
    return digest.hexdigest()


def _encode(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(type(value).__name__)


def evaluation_scope(state, context, schema):
    identity = getattr(context.model_gateway, "evaluation_identity", None)
    if identity is None:
        return None
    fields = ("run_id", "thread_id", "question", "conversation_summary", "recent_messages",
              "current_date", "timezone", "requirements", "evidence_contract_version",
              "research_brief", "delivery_plan", "decomposition_degraded")
    payload = {"state": {k: state.get(k) for k in fields}, "workspace": context.workspace_id,
               "corpus": context.source_evidence_ids, "model": identity, "rules": rule_digest(),
               "schema": schema.model_json_schema(), "day": context.clock.now().date()}
    try:
        return hashlib.sha256(json.dumps(payload, default=_encode, ensure_ascii=False,
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    except (TypeError, ValueError):
        return None
