"""Reference answers/tools stay score-side; view traces identify real input spans."""

import json

import pytest

from deeptrace.domain import ResearchMode
from deeptrace.eval import Corpus, ScriptedResearchModel, run_matrix
from deeptrace.eval.dataset import CorpusDocument, EvalQuestion
from deeptrace.eval.trajectory import TrajectoryRecorder


@pytest.mark.asyncio
async def test_all_modes_keep_gold_and_reference_tools_out_of_every_model_input():
    oracle = "ORACLE_SENTINEL_5d371"
    question = EvalQuestion(
        id="scope",
        question="Store scope",
        gold_answer=oracle,
        gold_urls=[f"https://gold.example/{oracle}"],
        reference_tool_calls=[{"name": "read_evidence", "args": {"query": oracle}}],
    )
    corpus = Corpus(
        [
            CorpusDocument(
                doc_id="store",
                url="https://example.com/store",
                title="Store",
                body="Store shares facts across threads.",
            )
        ]
    )
    records = await run_matrix(
        [question],
        corpus,
        model_factory=ScriptedResearchModel,
        modes=tuple(ResearchMode),
    )
    assert len(records) == 3
    for record in records:
        assert record.status == "completed"
        assert oracle not in json.dumps(record.trajectory["model_messages"])
        assert "reference_tool_calls" not in json.dumps(
            record.trajectory["model_messages"]
        )
        assert any(
            c["tool"] == "read_evidence" and c["ok"]
            for c in record.trajectory["tool_executions"]
        )
        views = record.trajectory.get("evidence_views")
        assert views, (
            "exact model-visible view events are missing from the exported trace"
        )
        assert {p["stage"] for p in views} >= {"evaluation", "response"}
        assert all("body" not in p and "text" not in p for p in views)
        sources = {s["id"]: s for s in record.evidence}
        for p in views:
            assert 0 <= p["start"] < p["end"] <= len(sources[p["evidence_id"]]["body"])


def test_view_trace_drops_prose_unknown_fields_and_bounds_event_count():
    recorder = TrajectoryRecorder()
    assert hasattr(recorder, "record_view"), "view metadata export not implemented"
    for _ in range(513):
        recorder.record_view(
            {
                "stage": "evaluation",
                "evidence_id": "e1",
                "version": 1,
                "content_hash": "hash",
                "start": 0,
                "end": 4,
                "passage_id": "p1",
                "visibility": True,
                "body": "MUST_NOT_EXPORT",
                "provider_secret": "MUST_NOT_EXPORT",
            }
        )
    views = recorder.snapshot()["evidence_views"]
    assert len(views) == 512
    assert "MUST_NOT_EXPORT" not in json.dumps(views)
    assert views[0] == {
        "stage": "evaluation",
        "evidence_id": "e1",
        "version": 1,
        "content_hash": "hash",
        "start": 0,
        "end": 4,
        "passage_id": "p1",
        "visibility": True,
    }
