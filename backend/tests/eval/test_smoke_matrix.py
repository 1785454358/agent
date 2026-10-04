import asyncio

import pytest

from deeptrace.domain import ResearchMode
from deeptrace.eval import (
    Corpus,
    ScriptedResearchModel,
    default_corpus_path,
    default_dataset_path,
    load_corpus,
    load_questions,
    run_matrix,
    score_records,
)


@pytest.mark.eval
def test_matrix_completes_with_full_gold_coverage() -> None:
    questions = load_questions(default_dataset_path())
    corpus = Corpus(load_corpus(default_corpus_path()))

    records = asyncio.run(
        run_matrix(
            questions,
            corpus,
            model_factory=ScriptedResearchModel,
            run_prefix="test-smoke",
        )
    )

    assert len(records) == len(questions) * len(ResearchMode)
    for record in records:
        assert record.termination_reason == "completed", record
        assert record.answered, record
        assert record.evidence_ids, record
        assert record.cited_evidence_ids, record

    report = score_records(records, questions)
    assert report.runs == len(records)
    assert {mode.mode for mode in report.modes} == {m.value for m in ResearchMode}
    for mode in report.modes:
        assert mode.mean_gold_coverage == 1.0, mode
        assert mode.citation_validity == 1.0, mode
        assert mode.termination_reasons == {"completed": len(questions)}


def test_single_mode_selection_limits_runs() -> None:
    questions = load_questions(default_dataset_path())[:1]
    corpus = Corpus(load_corpus(default_corpus_path()))

    records = asyncio.run(
        run_matrix(
            questions,
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            run_prefix="test-single",
        )
    )

    assert len(records) == 1
    assert records[0].mode == "workflow"
