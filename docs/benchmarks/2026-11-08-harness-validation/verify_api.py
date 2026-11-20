"""Exercise production assembly and HTTP routes with deterministic providers.

Run from backend: .venv/Scripts/python ../docs/benchmarks/2026-11-08-harness-validation/verify_api.py
Only model, search provider and page fetch transport are replaced. Runtime,
gateways, budgets, SQL checkpoints, evidence/ledger stores and API are real.
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from deeptrace.api import create_app
from deeptrace.application import assembly
from deeptrace.config import Settings
from deeptrace.domain.run import TERMINAL_STATUSES
from deeptrace.eval import Corpus, CorpusDocument, ScriptedResearchModel
from deeptrace.eval.env import CorpusFetcher
from deeptrace.runtime.local import LocalResearchRuntime


class DeterministicModel(ScriptedResearchModel):
    async def invoke(self, *, role, messages, tools=None):
        prompt = str(messages[-1].content)
        if role == "researcher" and "SOURCE_CANDIDATES_JSON:\n" in prompt:
            candidates = json.loads(prompt.split("SOURCE_CANDIDATES_JSON:\n", 1)[1])
            return AIMessage(content=json.dumps({"selected": [row["id"] for row in candidates]}))
        if role == "responder" and "ANSWER_REVIEW_JSON:\n" in prompt:
            return AIMessage(content=json.dumps({
                "content": "Shared runtime with durable checkpoints [1].",
                "issues": [], "unanswered_points": ["The fixture leaves one requested boundary unanswered."],
            }))
        return await super().invoke(role=role, messages=messages, tools=tools)


def wait_terminal(client, run_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/researches/{run_id}")
        response.raise_for_status()
        data = response.json()
        if data["status"] in TERMINAL_STATUSES:
            return data
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not terminate")


def verify(root, *, budget=240, review=False, trace_output=None):
    corpus = Corpus([CorpusDocument(doc_id="alpha", url="https://example.com/alpha",
        title="alpha beta", body="alpha beta describes a shared runtime and durable checkpoints.")])

    class SearchProvider:
        def __init__(self, **kwargs):
            pass

        def search(self, *, query, max_results, **kwargs):
            return {"results": corpus.search(query, limit=max_results)}

    settings = Settings("fixture", "https://example.com/v1", "fixture", "fixture",
        memory_retrieval="lexical", response_fact_review=review, max_tool_calls=budget)
    results = []
    with (
        patch.object(assembly, "ChatModelGateway", lambda *args, **kwargs: DeterministicModel()),
        patch.object(assembly, "AsyncWebFetcher", lambda **kwargs: CorpusFetcher(corpus)),
        patch.object(assembly, "TavilyClient", SearchProvider),
    ):
        bundle = assembly.build_harness_runtime(settings, runs_dir=root / "stores")

        def runtime():
            return LocalResearchRuntime(settings, root / "runs", application=bundle.service,
                context_factory=bundle.context_factory, release_run=bundle.release_run,
                trace_store=bundle.trace_store)

        with TestClient(create_app(settings=settings, runtime=runtime())) as client:
            try:
                for mode in ("workflow", "plan_execute", "multi_agent"):
                    response = client.post("/researches", json={"question": "alpha beta", "mode": mode})
                    response.raise_for_status()
                    data = wait_terminal(client, response.json()["id"])
                    if budget and not review:
                        assert data["status"] == "completed", data
                        assert data["finish_reason"] == "completed", data
                        assert data["research_sufficiency"] == "sufficient", data
                        assert data["sources"] and "[1]" in data["answer"], data
                    elif budget and review:
                        assert data["status"] == "partial", data
                        assert data["termination_reason"] == "answer_review_incomplete", data
                        assert data["finish_reason"] == "response_error", data
                        assert data["research_sufficiency"] == "sufficient", data
                    else:
                        assert data["status"] == "partial", data
                        assert data["finish_reason"] == "budget_exhausted", data
                    stream = client.get(f"/researches/{data['id']}/events")
                    assert stream.status_code == 200 and "event: done" in stream.text
                    saved = json.loads((root / "runs" / f"{data['id']}.json").read_text("utf-8"))
                    assert saved["finish_reason"] == data["finish_reason"]
                    assert saved["research_sufficiency"] == data["research_sufficiency"]
                    results.append({key: data[key] for key in (
                        "id", "mode", "status", "finish_reason", "termination_reason",
                        "research_sufficiency", "sources", "unresolved_gaps",
                    )} | {"sse_done": True, "budget": budget, "review_gap": review})
                    if trace_output is not None:
                        trace = client.get(f"/researches/{data['id']}/trace/export")
                        trace.raise_for_status()
                        exported = trace.json()
                        assert exported["summary"]["complete"], exported
                        by_id = {s["span_id"]: s for s in exported["spans"]}
                        assert all(s["parent_span_id"] is None or s["parent_span_id"] in by_id
                                   for s in exported["spans"])
                        assert all(e["span_id"] in by_id for e in exported["events"])
                        first_page = client.get(f"/researches/{data['id']}/trace?limit=2").json()
                        assert first_page["has_more"] and len(first_page["spans"]) == 2
                        trace_output.mkdir(parents=True, exist_ok=True)
                        name = f"{mode}-{'budget' if not budget else ('review' if review else 'success')}-trace.json"
                        (trace_output / name).write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")
                        results[-1].update(trace_id=exported["trace_id"], trace_summary=exported["summary"], trace_file=name)
                with TestClient(create_app(settings=settings, runtime=runtime())) as restarted:
                    for result in results:
                        restored = restarted.get(f"/researches/{result['id']}").json()
                        for key in ("status", "finish_reason", "research_sufficiency"):
                            assert restored[key] == result[key]
                        result["restart_restored"] = True
                        if trace_output is not None:
                            restored_trace = restarted.get(f"/researches/{result['id']}/trace").json()
                            assert restored_trace["trace_id"] == result["trace_id"]
                            assert restored_trace["summary"]["span_count"] == result["trace_summary"]["span_count"]
                    if trace_output is not None:
                        for result in results:
                            assert restarted.delete(f"/researches/{result['id']}").status_code == 200
                            assert restarted.get(f"/researches/{result['id']}/trace").status_code == 404
                            assert restarted.portal.call(bundle.trace_store.read, result['id']) == ([], [])
            finally:
                client.portal.call(bundle.aclose)
    return results


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="harness-api-validation-") as temporary:
        root = Path(temporary)
        results = (verify(root / "success") + verify(root / "budget", budget=0)
                   + verify(root / "review", review=True))
    output = {"transport": "FastAPI TestClient / ASGI HTTP", "providers": "deterministic local fixtures",
        "checks": results}
    Path(__file__).with_name("api-results.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True, indent=2))
