"""Replay the historical empty-claims failure using its original evidence."""

import asyncio
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import uuid

from deeptrace.application.assembly import build_harness_runtime
from deeptrace.config import Settings
from deeptrace.domain import ResearchOutcome, ResponseInput, ResponseMode
from deeptrace.responses.graph import build_answer_graph
from deeptrace.tools.evidence_store import EvidenceDraft


async def main():
    source_dir = Path("../docs/benchmarks/2026-11-16-eight-case-live/optimized/insufficient_evidence-test-01")
    old = json.loads((source_dir / "result.json").read_text("utf8"))
    sources = json.loads((source_dir / "sources.json").read_text("utf8"))
    folder = Path("runs") / ("delivery-replay-20261117-" + uuid.uuid4().hex[:6])
    settings = replace(Settings.from_env(), runtime_mode="local", mysql_dsn="", redis_url="",
                       memory_retrieval="lexical")
    bundle = build_harness_runtime(settings, runs_dir=folder / "state")
    context = bundle.context_factory("replay-" + uuid.uuid4().hex[:12])
    try:
        for source in sources:
            record = await context.evidence_store.ingest(context.workspace_id, EvidenceDraft(
                canonical_url=source["canonical_url"], title=source["title"],
                body=source["body"], media_type=source["media_type"],
                fetched_at=datetime.fromisoformat(source["fetched_at"]), source_quality=source["source_quality"],
            ))
            assert record.id == source["id"]
        payload = ResponseInput(
            question="Which structured-output strategy does the frozen documentation name as universally cheapest and lowest-latency, and what cost savings does it state?",
            response_mode=ResponseMode.ANSWER,
            research_outcome=ResearchOutcome.model_validate(old["research_outcome"]),
            active_evidence_ids=old["research_outcome"]["evidence_ids"],
            verified_finding_ids=[],
        )
        result = await build_answer_graph().ainvoke({"response_input": payload}, context=context)
        outcome = result["outcome"]
        (folder / "result.json").write_text(outcome.model_dump_json(indent=2), encoding="utf8")
        (folder / "answer.md").write_text(outcome.content, encoding="utf8")
        print(folder.resolve(), outcome.partial_reason, len(outcome.content), len(outcome.citations), flush=True)
        print(outcome.content, flush=True)
    finally:
        await bundle.aclose()


if __name__ == "__main__":
    asyncio.run(main())
