"""Real-API smoke test (marked `real`; runs only with keys and -m real).

Validates the production cutover path: Settings → assembly → top-level runtime
graph → real Tavily search → real page fetch → real model calls → cited answer.
"""

from __future__ import annotations

import pytest

from deeptrace.config import Settings


@pytest.mark.real
@pytest.mark.asyncio
async def test_real_workflow_run_returns_cited_answer() -> None:
    pytest.importorskip("langchain_openai")
    settings = Settings.from_env()
    if not getattr(settings, "openai_api_key", ""):
        pytest.skip("openai_api_key is not configured")

    from deeptrace.application.assembly import build_harness_runtime
    from deeptrace.application.research import ApplicationResearchRequest
    from deeptrace.domain import ResearchMode

    bundle = build_harness_runtime(settings, runs_dir="runs")
    try:
        outcome = await bundle.service.invoke(
            ApplicationResearchRequest(
                run_id="real-smoke-1",
                thread_id="real-smoke-1",
                question="LangGraph 的 checkpoint 机制是什么？",
                mode=ResearchMode.WORKFLOW,
            ),
            config={"configurable": {"thread_id": "real-smoke-1"}},
            context=bundle.context_factory("real-smoke-1"),
        )
    finally:
        await bundle.aclose()
    assert outcome.partial_reason is None
    assert outcome.cited_evidence_ids
    assert len(outcome.content) > 20
