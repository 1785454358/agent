"""Compare real model calls over supplied immutable source bodies.

Run from backend with --sources <JSON [{url,title,raw_content}]>
--question <UTF-8 file> --output <new directory>. No live search or fetch.
The development fixtures supply in-memory tool adapters, not model answers.
"""

import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langgraph.checkpoint.memory import InMemorySaver
from deeptrace.application.model_provider import build_model_gateway
from deeptrace.application.research import ApplicationResearchRequest, ResearchApplicationService
from deeptrace.config.settings import Settings
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.harness.graph import build_agent_runtime_graph
from deeptrace.harness.model_budget import RunBudgetModelGateway
from deeptrace.harness.model_gateway import ChatModelGateway
from deeptrace.harness.registry import ResponseGraphRegistry, ResponseRegistration, StrategyRegistration, StrategyRegistry
from deeptrace.responses import build_answer_graph
from deeptrace.strategies import build_workflow_research_graph, build_plan_execute_research_graph, build_multi_agent_research_graph
from deeptrace.tools.evidence_store import EvidenceDraft
from strategies.fixtures import build_gateway_fixture, TENANT_ID


async def compare(args):
    args.output.mkdir(parents=True, exist_ok=False)
    question = args.question.read_text(encoding="utf8")
    sources = json.loads(args.sources.read_text(encoding="utf8"))
    settings = Settings.from_env()
    manifest = [{"url": row["url"], "sha256": hashlib.sha256(row["raw_content"].encode()).hexdigest(),
                 "chars": len(row["raw_content"])} for row in sources]
    (args.output / "sources.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
    summaries = []
    for mode, builder in [(ResearchMode.WORKFLOW, build_workflow_research_graph),
                          (ResearchMode.PLAN_EXECUTE, build_plan_execute_research_graph),
                          (ResearchMode.MULTI_AGENT, build_multi_agent_research_graph)]:
        if args.modes and mode.value not in args.modes:
            continue
        print("START", mode.value, flush=True)
        identity = "frozen-" + mode.value
        model = RunBudgetModelGateway(build_model_gateway(settings, ChatModelGateway), run_id=identity,
            max_calls=settings.max_model_calls, max_input_tokens=settings.max_input_tokens,
            max_seconds=settings.research_max_seconds, finishing_calls=min(3, settings.max_model_calls - 1))
        fixture = build_gateway_fixture(model_gateway=model, run_ids=(identity,))
        model.event_sink = fixture.context.event_sink
        records = [await fixture.evidence_store.ingest(TENANT_ID, EvidenceDraft(
            canonical_url=row["url"], title=row["title"], body=row["raw_content"],
            media_type="text/plain", fetched_at=datetime(2026, 11, 18, tzinfo=UTC), source_quality=0.9)) for row in sources]
        context = replace(fixture.context, source_evidence_ids=frozenset(r.id for r in records),
            tool_gateway=fixture.gateway._inner.with_source_scope(frozenset(r.id for r in records)),
            response_fact_review=True)
        strategies, responses = StrategyRegistry(), ResponseGraphRegistry()
        strategies.register(StrategyRegistration(mode, builder(build_batch_research_graph())))
        responses.register(ResponseRegistration(ResponseMode.ANSWER, build_answer_graph()))
        graph = build_agent_runtime_graph(strategies, responses,
            checkpointer=InMemorySaver(serde=create_harness_checkpoint_serializer()))
        config = {"configurable": {"thread_id": identity}}
        started = time.perf_counter()
        error = None
        answer = ""
        research = None
        application = None
        try:
            application = await ResearchApplicationService(graph).invoke(ApplicationResearchRequest(
                run_id=identity, thread_id=identity, question=question, mode=mode,
                response_mode=ResponseMode.ANSWER), config=config, context=context)
            snapshot = await graph.aget_state(config)
            turn = snapshot.values["turn"]
            research = turn.get("research_outcome")
            response = turn.get("response_outcome")
            answer = response.content if response else ""
        except Exception as exc:
            error = type(exc).__name__
        summary = {"mode": mode.value, "seconds": round(time.perf_counter()-started, 3),
            "usage": model.usage_payload(), "error": error,
            "status": application.status if application else "failed",
            "termination_reason": application.termination_reason if application else error,
            "response": application.response_outcome.model_dump(mode="json")
                        if application and application.response_outcome else None,
            "research": research.model_dump(mode="json") if research else None}
        folder = args.output / mode.value
        folder.mkdir()
        (folder / "answer.md").write_text(answer, encoding="utf8")
        (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
        (folder / "events.json").write_text(json.dumps(fixture.context.event_sink.events, ensure_ascii=False,
            default=str), encoding="utf8")
        summaries.append(summary)
        print("FINISH", mode.value, summary["seconds"], model.used_calls, error, flush=True)
    (args.output / "summaries.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--question", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--modes", nargs="*", choices=[m.value for m in ResearchMode])
    asyncio.run(compare(parser.parse_args()))
