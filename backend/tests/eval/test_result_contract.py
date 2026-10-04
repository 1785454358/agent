import asyncio

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


class InvalidResponder(ScriptedResearchModel):
    async def invoke(self, *, role, messages, tools=None):
        if role == "responder":
            return "not valid JSON"
        return await super().invoke(role=role, messages=messages, tools=tools)


def test_response_failure_is_not_counted_as_completed_research_run():
    questions = load_questions(default_dataset_path())[:1]
    records = asyncio.run(
        run_matrix(
            questions,
            Corpus(load_corpus(default_corpus_path())),
            model_factory=InvalidResponder,
            modes=(ResearchMode.WORKFLOW,),
        )
    )

    assert records[0].status == "partial"
    assert records[0].research_termination_reason == "completed"
    assert records[0].termination_reason != "completed"
    assert score_records(records, questions).modes[0].completed == 0


def test_completed_record_exports_real_decisions_and_execution_results():
    questions = load_questions(default_dataset_path())[:1]
    records = asyncio.run(
        run_matrix(
            questions,
            Corpus(load_corpus(default_corpus_path())),
            model_factory=ScriptedResearchModel,
            modes=(ResearchMode.WORKFLOW,),
        )
    )

    record = records[0]
    assert record.status == "completed"
    calls = [
        call for turn in record.trajectory["model_turns"] for call in turn["tool_calls"]
    ]
    assert any(call["name"] == "search_web" for call in calls)
    assert any(call["name"] == "fetch_page" for call in calls)
    executions = record.trajectory["tool_executions"]
    assert len(executions) == record.tool_calls
    assert any(row["tool"] == "fetch_page" and row["ok"] for row in executions)
    assert all(
        row["caller_id"] and row["request_id"] and row["call_id"] for row in executions
    )


def test_cli_exports_reference_free_samples_as_unmeasured(tmp_path):
    import json

    from deeptrace.eval.__main__ import main

    assert main(["--modes", "workflow", "--out", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / "tool_eval.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert len(payload["provenance"]["dataset_sha256"]) == 64
    assert len(payload["provenance"]["corpus_sha256"]) == 64
    assert payload["provenance"]["model_kind"] == "scripted"
    assert all(row["reference_tool_calls"] is None for row in payload["samples"])
    assert all(row["trajectory"]["model_turns"] for row in payload["samples"])
