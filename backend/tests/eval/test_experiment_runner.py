import asyncio
import json

import pytest

from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.eval import (
    Corpus,
    ScriptedResearchModel,
    default_corpus_path,
    default_dataset_path,
    load_corpus,
    load_questions,
)
from deeptrace.eval.runner import run_matrix


class LongAnswerModel(ScriptedResearchModel):
    async def invoke(self, *, role, messages, tools=None):
        if role == "responder":
            return json.dumps(
                {"content": "解释 " * 2000 + " unique-tail-after-4000 [1]"}
            )
        return await super().invoke(role=role, messages=messages, tools=tools)


def inputs():
    return load_questions(default_dataset_path())[:1], Corpus(
        load_corpus(default_corpus_path())
    )


@pytest.mark.asyncio
async def test_complete_answer_evidence_and_model_visible_messages_are_retained():
    questions, corpus = inputs()
    records = await run_matrix(
        questions,
        corpus,
        model_factory=LongAnswerModel,
        modes=(ResearchMode.WORKFLOW,),
        response_mode=ResponseMode.REPORT,
    )
    record = records[0]
    assert "unique-tail-after-4000" in record.answer
    assert len(record.answer) > 4000
    assert record.evidence
    for evidence in record.evidence:
        assert evidence["body"] == corpus.document_for(evidence["url"]).body
    assert record.trajectory["model_messages"]
    assert any(
        "原始任务：" in str(turn["messages"])
        for turn in record.trajectory["model_messages"]
    )
    assert record.trajectory["tool_results"]
    assert record.usage["provider_attempts"] is None
    assert record.usage["input_tokens"] is None


@pytest.mark.asyncio
async def test_resume_keeps_completed_samples_without_model_calls(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    questions, corpus = inputs()
    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        first = await run_matrix(
            questions,
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            store=store,
        )

    def forbidden_factory():
        raise AssertionError("resume must not build a model for completed work")

    with ExperimentStore(tmp_path, {"schema_version": 2}, resume=True) as store:
        second = await run_matrix(
            questions,
            corpus,
            model_factory=forbidden_factory,
            modes=(ResearchMode.WORKFLOW,),
            store=store,
        )
    assert second[0].answer == first[0].answer
    assert second[0].model_calls == first[0].model_calls


@pytest.mark.asyncio
async def test_resume_retains_failed_sample_instead_of_seeking_success(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore
    from deeptrace.eval.runner import RunRecord

    questions, corpus = inputs()
    run_id = f"eval-{questions[0].id}-workflow"
    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        store.claim(run_id)
        store.save(
            RunRecord(
                question_id=questions[0].id,
                question=questions[0].question,
                run_id=run_id,
                mode="workflow",
                status="failed",
                termination_reason="execution_error",
                answered=False,
                system_error="TimeoutError",
                model_calls=2,
            ).model_dump(mode="json")
        )

    def forbidden_factory():
        pytest.fail("failed attempts must be retained, not rerun")

    with ExperimentStore(tmp_path, {"schema_version": 2}, resume=True) as store:
        records = await run_matrix(
            questions,
            corpus,
            model_factory=forbidden_factory,
            modes=(ResearchMode.WORKFLOW,),
            store=store,
        )
    assert records[0].status == "failed"
    assert records[0].model_calls == 2


@pytest.mark.asyncio
async def test_records_are_saved_before_next_factory_is_called(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    questions, corpus = inputs()
    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        factories = 0

        def factory():
            nonlocal factories
            if factories:
                assert (
                    store.load(f"eval-{questions[0].id}-workflow-r0")["status"]
                    == "completed"
                )
            factories += 1
            return ScriptedResearchModel()

        records = await run_matrix(
            questions,
            corpus,
            model_factory=factory,
            modes=(ResearchMode.WORKFLOW,),
            repeats=2,
            store=store,
        )
    assert len(records) == 2


@pytest.mark.asyncio
async def test_model_ceiling_prevents_further_paid_boundary_calls(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore
    from deeptrace.eval.experiment import EvaluationLimits

    questions, corpus = inputs()
    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        records = await run_matrix(
            questions,
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            limits=EvaluationLimits(max_model_calls=1),
            store=store,
        )
        saved = store.load(records[0].run_id)
    assert records[0].status != "completed"
    assert records[0].model_calls == 1
    assert saved["status"] == records[0].status


@pytest.mark.asyncio
async def test_cancellation_propagates_and_keeps_ambiguous_claim(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    entered = asyncio.Event()

    class CancelledModel:
        async def invoke(self, **kwargs):
            entered.set()
            await asyncio.Event().wait()

    questions, corpus = inputs()
    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        task = asyncio.create_task(
            run_matrix(
                questions,
                corpus,
                model_factory=CancelledModel,
                modes=(ResearchMode.WORKFLOW,),
                store=store,
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ValueError, match="incomplete"):
            store.load(f"eval-{questions[0].id}-workflow")


@pytest.mark.asyncio
async def test_batch_logical_limit_is_shared_and_failed_samples_are_saved(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore
    from deeptrace.eval.experiment import EvaluationLimits

    questions, corpus = inputs()
    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        records = await run_matrix(
            questions,
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
            repeats=2,
            store=store,
            limits=EvaluationLimits(max_batch_model_calls=1),
        )
    assert sum(record.model_calls for record in records) == 1
    assert all(record.status != "completed" for record in records)
    assert len(list((tmp_path / "samples").glob("*.json"))) == 2


@pytest.mark.asyncio
async def test_timeout_preserves_fetched_sources_before_answer_failed():
    from deeptrace.eval.experiment import EvaluationLimits

    class SlowResponder(ScriptedResearchModel):
        async def invoke(self, *, role, messages, tools=None):
            if role == "responder":
                await asyncio.sleep(10)
            return await super().invoke(role=role, messages=messages, tools=tools)

    questions, corpus = inputs()
    records = await run_matrix(
        questions,
        corpus,
        model_factory=SlowResponder,
        modes=(ResearchMode.WORKFLOW,),
        limits=EvaluationLimits(run_timeout_seconds=1),
    )
    assert records[0].status == "failed"
    assert records[0].system_error == "TimeoutError"
    assert records[0].evidence
    assert (
        records[0].evidence[0]["body"]
        == corpus.document_for(records[0].evidence[0]["url"]).body
    )
