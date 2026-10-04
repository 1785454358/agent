import asyncio

from deeptrace.domain import ResearchMode
from deeptrace.eval import (
    Corpus,
    ScriptedJudgeModel,
    ScriptedResearchModel,
    default_corpus_path,
    default_dataset_path,
    load_corpus,
    load_questions,
    run_matrix,
    score_records,
)


def test_judge_scores_are_collected_and_aggregated() -> None:
    questions = load_questions(default_dataset_path())[:1]
    corpus = Corpus(load_corpus(default_corpus_path()))

    records = asyncio.run(
        run_matrix(
            questions,
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            run_prefix="test-judge",
            judge_factory=ScriptedJudgeModel,
        )
    )

    assert len(records) == 1
    assert records[0].judge is not None
    report = score_records(records, questions)
    assert report.modes[0].judge_runs == 1
    assert report.modes[0].mean_faithfulness == 4.0


def test_repeats_produce_one_record_per_repeat() -> None:
    questions = load_questions(default_dataset_path())[:1]
    corpus = Corpus(load_corpus(default_corpus_path()))

    records = asyncio.run(
        run_matrix(
            questions,
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            run_prefix="test-repeat",
            repeats=3,
        )
    )

    assert len(records) == 3
    assert sorted(record.repeat_index for record in records) == [0, 1, 2]
    assert len({record.run_id for record in records}) == 3
