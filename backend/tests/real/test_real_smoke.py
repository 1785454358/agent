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

    service, context_factory = build_harness_runtime(settings)
    run_id = "real-smoke-1"
    outcome = await service.invoke(
        ApplicationResearchRequest(
            run_id=run_id,
            thread_id=run_id,
            question="LangGraph 的 checkpoint 机制是什么？",
            mode=ResearchMode.WORKFLOW,
        ),
        config={"configurable": {"thread_id": run_id}},
        context=context_factory(run_id),
    )

    assert outcome.partial_reason is None
    assert outcome.cited_evidence_ids
    assert len(outcome.content) > 20
