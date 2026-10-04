"""Tier 2 real-model evaluation smoke test (marked `real`).

Runs the offline corpus with a real OpenAI-compatible model and an LLM judge.
Requires credentials; skipped automatically when they are absent.
"""

from __future__ import annotations

import pytest

from deeptrace.config import Settings


@pytest.mark.real
@pytest.mark.asyncio
async def test_real_eval_produces_bounded_judge_scores() -> None:
    pytest.importorskip("langchain_openai")
    settings = Settings.from_env()
    if not getattr(settings, "openai_api_key", ""):
        pytest.skip("openai_api_key is not configured")

    from deeptrace.domain import ResearchMode
    from deeptrace.eval import (
        Corpus,
        default_corpus_path,
        default_dataset_path,
        load_corpus,
        load_questions,
        run_matrix,
    )
    from deeptrace.eval.real import build_real_model_factory

    factory = build_real_model_factory(settings)
    questions = load_questions(default_dataset_path())[:1]
    corpus = Corpus(load_corpus(default_corpus_path()))

    records = await run_matrix(
        questions,
        corpus,
        model_factory=factory,
        modes=(ResearchMode.WORKFLOW,),
        repeats=1,
        run_prefix="real-eval",
        judge_factory=factory,
    )

    assert len(records) == 1
    # Real models may end partial; the judge contract must still hold.
    assert records[0].judge is not None
    for field in (
        records[0].judge.faithfulness,
        records[0].judge.answer_correctness,
        records[0].judge.source_coverage,
        records[0].judge.citation_accuracy,
        records[0].judge.coherence,
    ):
        assert 1 <= field <= 5
