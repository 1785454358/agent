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
    render_markdown,
    run_matrix,
    score_records,
)


def run(judge_factory=None):
    questions = load_questions(default_dataset_path())[:1]
    records = asyncio.run(
        run_matrix(
            questions,
            Corpus(load_corpus(default_corpus_path())),
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            judge_factory=judge_factory,
        )
    )
    return records, score_records(records, questions)


def test_unmeasured_judge_is_null_not_zero():
    records, report = run()
    assert report.modes[0].mean_faithfulness is None
    assert report.modes[0].judge_attempted == 0
    assert records[0].judge_error is None


class BrokenJudge:
    async def invoke(self, **kwargs):
        raise RuntimeError("private-provider-error-not-for-export")


def test_failed_judge_is_reported_without_fabricating_zero():
    records, report = run(BrokenJudge)
    assert records[0].status == "completed"
    assert records[0].judge is None
    assert records[0].judge_error == "RuntimeError"
    assert report.modes[0].judge_attempted == 1
    assert report.modes[0].judge_failures == 1
    assert report.modes[0].mean_faithfulness is None
    markdown = render_markdown(report)
    assert "legacy_custom" in markdown
    assert "N/A" in markdown
    assert "private-provider-error-not-for-export" not in markdown


def test_partial_judge_coverage_does_not_dilute_successful_scores():
    questions = load_questions(default_dataset_path())[:1]
    judges = iter([BrokenJudge(), ScriptedJudgeModel()])
    records = asyncio.run(
        run_matrix(
            questions,
            Corpus(load_corpus(default_corpus_path())),
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            repeats=2,
            judge_factory=lambda: next(judges),
        )
    )
    mode = score_records(records, questions).modes[0]
    assert mode.judge_runs == 1
    assert mode.judge_attempted == 2
    assert mode.judge_failures == 1
    assert mode.mean_faithfulness == 4.0


def test_failed_execution_keeps_record_and_matrix_continues(monkeypatch):
    from deeptrace.application.research import ResearchApplicationService

    original = ResearchApplicationService.invoke
    failed = False

    async def first_fails(self, *args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("private-execution-error")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(ResearchApplicationService, "invoke", first_fails)
    questions = load_questions(default_dataset_path())[:1]
    records = asyncio.run(
        run_matrix(
            questions,
            Corpus(load_corpus(default_corpus_path())),
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            repeats=2,
        )
    )
    assert [record.status for record in records] == ["failed", "completed"]
    assert records[0].system_error == "RuntimeError"
    assert records[0].answered is False
    assert records[0].termination_reason == "execution_error"
    assert score_records(records, questions).modes[0].completed == 1


def test_cli_returns_failure_code_for_partial_runs(tmp_path):
    from deeptrace.eval.__main__ import main
    from deeptrace.eval.dataset import default_corpus_path

    dataset = tmp_path / "unanswerable.jsonl"
    dataset.write_text(
        '{"id":"q","question":"zzzz_unmatched","gold_urls":[]}', encoding="utf-8"
    )
    assert (
        main(
            [
                "--dataset",
                str(dataset),
                "--corpus",
                str(default_corpus_path()),
                "--modes",
                "workflow",
            ]
        )
        == 1
    )
