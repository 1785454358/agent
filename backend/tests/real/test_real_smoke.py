"""Real-API smoke test (marked `real`; runs only with keys and -m real).

Validates the production cutover path: Settings → assembly → top-level runtime
graph → real Tavily search → real page fetch → real model calls → cited answer.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace

import pytest

from deeptrace.config import Settings


@pytest.mark.real
# The installed model SDK caches async HTTP clients across model instances.
# Real API tests share the production-style event loop across their lifetimes.
@pytest.mark.asyncio(loop_scope="session")
async def test_real_workflow_run_returns_cited_answer(tmp_path) -> None:
    pytest.importorskip("langchain_openai")
    settings = replace(
        Settings.from_env(),
        runtime_mode="local",
        mysql_dsn="",
        redis_url="",
        memory_retrieval="lexical",
        agent_max_iterations=12,
    )
    if not getattr(settings, "openai_api_key", ""):
        pytest.skip("openai_api_key is not configured")

    from deeptrace.application.assembly import build_harness_runtime
    from deeptrace.application.research import ApplicationResearchRequest
    from deeptrace.domain import ResearchMode

    run_id = f"real-smoke-{uuid.uuid4().hex[:8]}"
    # the context factory is keyed by RUN id (budget scopes are registered per
    # run); the thread may differ when a caller continues a conversation
    thread_id = f"real-thread-{uuid.uuid4().hex[:8]}"
    bundle = build_harness_runtime(settings, runs_dir=tmp_path)
    context = bundle.context_factory(run_id)
    counts = {"model_calls": 0, "tool_calls": 0}
    tool_results: list[dict] = []

    class BoundedModel:
        async def invoke(self, **kwargs):
            if counts["model_calls"] >= settings.max_model_calls:
                raise RuntimeError("real smoke model-call limit reached")
            counts["model_calls"] += 1
            response = await context.model_gateway.invoke(**kwargs)
            (
                tmp_path / f"model-{counts['model_calls']:02d}-{kwargs['role']}.json"
            ).write_text(
                json.dumps(
                    {
                        "messages": [
                            message.model_dump(mode="json")
                            for message in kwargs["messages"]
                        ],
                        "content": response.content,
                        "usage": response.usage_metadata,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            if kwargs["role"] == "evaluator":
                from pydantic import ValidationError

                from deeptrace.strategies.model_io import payload_text
                from deeptrace.strategies.workflow.models import (
                    ReferenceWorkflowEvaluation,
                )

                errors = []
                try:
                    ReferenceWorkflowEvaluation.model_validate_json(
                        payload_text(response)
                    )
                except ValidationError as exc:
                    errors = [
                        {
                            "type": error["type"],
                            "loc": error["loc"],
                            "input_type": type(error.get("input")).__name__,
                        }
                        for error in exc.errors()
                    ]
                print(
                    json.dumps(
                        {
                            "role": "evaluator",
                            "finish_reason": response.response_metadata.get(
                                "finish_reason"
                            ),
                            "validation_errors": errors,
                        }
                    )
                )
            return response

    class BoundedTools:
        async def execute(self, **kwargs):
            if counts["tool_calls"] >= settings.max_tool_calls:
                raise RuntimeError("real smoke tool-call limit reached")
            counts["tool_calls"] += 1
            result = await context.tool_gateway.execute(**kwargs)
            tool_results.append(
                {
                    "tool": result.tool.value,
                    "ok": result.ok,
                    "error_code": result.error_code,
                    "evidence_count": len(result.evidence_ids),
                }
            )
            return result

    bounded_context = replace(
        context, model_gateway=BoundedModel(), tool_gateway=BoundedTools()
    )
    config = {"configurable": {"thread_id": thread_id}}
    try:
        async with asyncio.timeout(settings.research_max_seconds + 300):
            outcome = await bundle.service.invoke(
                ApplicationResearchRequest(
                    run_id=run_id,
                    thread_id=thread_id,
                    question="LangGraph 的 checkpoint 机制是什么？",
                    mode=ResearchMode.WORKFLOW,
                ),
                config=config,
                context=bounded_context,
            )
            snapshot = await bundle.service._graph.aget_state(config)
            turn = snapshot.values["turn"]
            (tmp_path / "outcomes.json").write_text(
                json.dumps(
                    {
                        "research": outcome.research_outcome.model_dump(mode="json"),
                        "response": outcome.response_outcome.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            assert outcome.status == turn["status"]
            assert outcome.research_outcome == turn["research_outcome"]
            assert outcome.response_outcome == turn["response_outcome"]
            assert (outcome.run_id, outcome.thread_id) == (run_id, thread_id)
            research = outcome.research_outcome
            assert research is not None
            assert outcome.executed_steps == research.executed_steps
            assert set(research.unresolved_gaps) <= set(outcome.unresolved_gaps)
            if (
                outcome.status == "completed"
                and outcome.response_outcome.partial_reason
            ):
                assert (
                    f"response:{outcome.response_outcome.partial_reason}"
                    in outcome.unresolved_gaps
                )
            assert outcome.termination_reason == "workflow_completed"
            print(
                json.dumps(
                    {
                        "status": outcome.status,
                        "termination_reason": outcome.termination_reason,
                        "executed_steps": outcome.executed_steps,
                        "sources": len(outcome.sources),
                        "unresolved_gaps": outcome.unresolved_gaps,
                        "tool_results": tool_results,
                        **counts,
                    }
                )
            )
            assert outcome.sources
            assert any(
                row["tool"] == "fetch_page" and row["ok"] for row in tool_results
            )
            assert outcome.status == "completed"
            assert outcome.termination_reason == "workflow_completed"
            assert outcome.response_outcome.partial_reason is None
            assert outcome.response_outcome.cited_evidence_ids
            assert len(outcome.response_outcome.content) > 20
            assert "[1]" in outcome.response_outcome.content
    finally:
        await bundle.aclose()
