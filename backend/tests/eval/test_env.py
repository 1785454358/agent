import asyncio

from deeptrace.eval import (
    Corpus,
    CorpusDocument,
    EvalFaults,
    ScriptedResearchModel,
    build_eval_context,
)
from deeptrace.eval.env import CorpusFetcher, CorpusSearch

_URL = "https://corpus.example/checkpoint"


def _corpus() -> Corpus:
    return Corpus(
        [
            CorpusDocument(
                doc_id="doc-a",
                url=_URL,
                title="LangGraph checkpoint 与恢复",
                body="checkpoint 保存可恢复状态并支持崩溃恢复。",
                tags=["checkpoint", "恢复"],
            ),
            CorpusDocument(
                doc_id="doc-b",
                url="https://corpus.example/unrelated",
                title="无关文档",
                body="与检索问题没有重叠词。",
                tags=["misc"],
            ),
        ]
    )


def test_search_ranks_matching_document_first() -> None:
    results = _corpus().search("checkpoint 崩溃恢复", limit=5)
    assert results
    assert results[0]["url"] == _URL


def test_search_without_overlap_returns_empty() -> None:
    assert _corpus().search("completely unrelated tokens", limit=5) == []


def test_fetcher_returns_success_document() -> None:
    document = asyncio.run(CorpusFetcher(_corpus()).fetch(_URL))
    assert document.status == "success"
    assert document.content
    assert document.canonical_url == _URL


def test_fetcher_fault_is_reported_as_failed() -> None:
    fetcher = CorpusFetcher(_corpus(), EvalFaults(fetch={_URL: "empty"}))
    document = asyncio.run(fetcher.fetch(_URL))
    assert document.status == "failed"
    assert document.content == ""


def test_search_fault_returns_error_payload() -> None:
    search = CorpusSearch(_corpus(), EvalFaults(search_queries=frozenset({"boom"})))
    response = asyncio.run(search.search("boom"))
    assert response["ok"] is False


def test_build_eval_context_wires_production_boundaries() -> None:
    env = build_eval_context(
        _corpus(), model_gateway=ScriptedResearchModel(), run_id="run-eval"
    )
    assert env.context.tool_gateway is env.tool_gateway
    assert env.context.model_gateway is env.model_gateway
    assert env.model_calls == 0
    assert env.tool_calls == 0
